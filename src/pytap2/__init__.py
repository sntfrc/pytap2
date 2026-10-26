"""A small, packet-oriented wrapper for OS TUN interfaces.

Linux uses ``/dev/net/tun``, macOS uses ``utun`` kernel control sockets, and
Windows uses the Wintun userspace API. Creating/configuring an interface
normally requires administrator/root privileges.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import ipaddress
import os
import platform
import socket
import struct
import subprocess
import uuid
from typing import Optional

if os.name != "nt":
    import fcntl


IFF_TUN = 0x0001
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000
_IFNAMSIZ = 16
_DEFAULT_MTU = 1500


class TapDeviceError(OSError):
    """Raised when a TUN interface cannot be created or operated."""


def _run(*args: str) -> None:
    """Run an interface configuration command and preserve its error output."""
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise TapDeviceError(f"Required command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise TapDeviceError(detail or f"Command failed: {' '.join(args)}") from exc


class _LinuxBackend:
    TUNSETIFF = 0x400454CA

    def __init__(self, name: Optional[str], mode: int, no_pi: bool) -> None:
        if mode not in (IFF_TUN, IFF_TAP):
            raise ValueError("mode must be IFF_TUN or IFF_TAP")
        self.fd = os.open("/dev/net/tun", os.O_RDWR)
        flags = mode | (IFF_NO_PI if no_pi else 0)
        request = struct.pack("16sH", (name or "").encode(), flags)
        try:
            result = fcntl.ioctl(self.fd, self.TUNSETIFF, request)
        except Exception:
            os.close(self.fd)
            raise
        self.name = result[:_IFNAMSIZ].split(b"\0", 1)[0].decode()
        self.no_pi = no_pi

    def read(self, size: int) -> bytes:
        return os.read(self.fd, size)

    def write(self, packet: bytes) -> int:
        return os.write(self.fd, packet)

    def fileno(self) -> int:
        return self.fd

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class _MacOSBackend:
    # Darwin kernel-control socket structures (native byte order).
    _CTL_INFO_SIZE = 96  # uint32 ctl_id + char ctl_name[96]
    _SOCKADDR_CTL = struct.Struct("=BBHII5I")
    _CTLIOCGINFO = 0xC0644E03
    _UTUN_CONTROL_NAME = b"com.apple.net.utun_control"
    _AF_SYSTEM = 32
    _AF_SYS_CONTROL = 2
    _SYSPROTO_CONTROL = 2
    _UTUN_OPT_IFNAME = 2

    def __init__(self, name: Optional[str], mode: int, no_pi: bool) -> None:
        if mode != IFF_TUN:
            raise ValueError("macOS utun supports layer-3 TUN devices only")
        if name and not name.startswith("utun"):
            raise ValueError("macOS interface names must be utunN")
        # For utun, sc_unit=0 asks the kernel to choose a free unit.
        self.sock = socket.socket(
            getattr(socket, "PF_SYSTEM", 32), socket.SOCK_DGRAM,
            self._SYSPROTO_CONTROL
        )
        try:
            info = bytearray(self._CTL_INFO_SIZE + 4)
            info[4:4 + len(self._UTUN_CONTROL_NAME)] = self._UTUN_CONTROL_NAME
            fcntl.ioctl(self.sock.fileno(), self._CTLIOCGINFO, info, True)
            ctl_id = struct.unpack_from("=I", info)[0]
            sockaddr = self._SOCKADDR_CTL.pack(
                self._SOCKADDR_CTL.size, self._AF_SYSTEM, 0,
                ctl_id, 0 if not name else int(name[4:]) + 1,
                0, 0, 0, 0, 0
            )
            self.sock.connect(sockaddr)
            self.name = self.sock.getsockopt(
                self._SYSPROTO_CONTROL, self._UTUN_OPT_IFNAME, 64
            ).split(b"\0", 1)[0].decode()
            if name and name != self.name:
                raise TapDeviceError(
                    f"Requested {name}, but macOS assigned {self.name}; "
                    "utun names are assigned by the kernel"
                )
        except Exception:
            self.sock.close()
            raise

    def read(self, size: int) -> bytes:
        packet = self.sock.recv(size + 4)
        if len(packet) < 4:
            return b""
        # utun prepends a 32-bit address-family value to every packet.
        return packet[4:]

    def write(self, packet: bytes) -> int:
        if not packet:
            return self.sock.send(packet)
        version = packet[0] >> 4
        if version == 4:
            family = socket.AF_INET
        elif version == 6:
            family = socket.AF_INET6
        else:
            raise ValueError("utun accepts only IPv4 or IPv6 packets")
        return max(0, self.sock.send(struct.pack("=I", family) + packet) - 4)

    def fileno(self) -> int:
        return self.sock.fileno()

    def close(self) -> None:
        self.sock.close()


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_uuid(cls, value: uuid.UUID) -> "_GUID":
        raw = value.bytes_le
        result = cls()
        ctypes.memmove(ctypes.byref(result), raw, 16)
        return result


class _WindowsBackend:
    ERROR_NO_MORE_ITEMS = 259
    ERROR_BUFFER_OVERFLOW = 111
    WAIT_OBJECT_0 = 0
    INFINITE = 0xFFFFFFFF

    def __init__(self, name: Optional[str], mode: int, no_pi: bool) -> None:
        if mode != IFF_TUN:
            raise ValueError("Wintun supports layer-3 TUN devices only")
        if not hasattr(ctypes, "WinDLL"):
            raise TapDeviceError("Wintun is available only on Windows")
        self.name = name or "pytap2"
        self._dll = self._load_dll()
        self._bind_api()
        adapter_type = "Wintun"
        adapter_guid = _GUID.from_uuid(
            uuid.uuid5(uuid.NAMESPACE_DNS, "pytap2:" + self.name)
        )
        self.adapter = self._create_adapter(
            self.name, adapter_type, ctypes.byref(adapter_guid)
        )
        if not self.adapter:
            raise ctypes.WinError(ctypes.get_last_error())
        self.session = self._start_session(self.adapter, 0x400000)
        if not self.session:
            error = ctypes.get_last_error()
            self._close_adapter(self.adapter)
            self.adapter = None
            raise ctypes.WinError(error)
        self._wait_event = self._get_read_wait_event(self.session)
        if not self._wait_event:
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._kernel32.WaitForSingleObject.restype = ctypes.c_uint32

    @staticmethod
    def _load_dll():
        candidates = []
        bundled = os.path.join(os.path.dirname(__file__), "wintun.dll")
        if os.path.isfile(bundled):
            candidates.append(bundled)
        found = ctypes.util.find_library("wintun")
        if found:
            candidates.append(found)
        candidates.append("wintun.dll")
        errors = []
        for candidate in candidates:
            try:
                return ctypes.WinDLL(candidate, use_last_error=True)
            except OSError as exc:
                errors.append(str(exc))
        raise TapDeviceError(
            "Could not load wintun.dll. Place the architecture-matched, "
            "signed Wintun DLL beside this module or on PATH. " + "; ".join(errors)
        )

    def _bind_api(self) -> None:
        pointer = ctypes.c_void_p
        self._create_adapter = self._dll.WintunCreateAdapter
        self._create_adapter.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                         ctypes.POINTER(_GUID)]
        self._create_adapter.restype = pointer
        self._start_session = self._dll.WintunStartSession
        self._start_session.argtypes = [pointer, ctypes.c_uint32]
        self._start_session.restype = pointer
        self._end_session = self._dll.WintunEndSession
        self._end_session.argtypes = [pointer]
        self._end_session.restype = None
        self._close_adapter = self._dll.WintunCloseAdapter
        self._close_adapter.argtypes = [pointer]
        self._close_adapter.restype = None
        self._receive_packet = self._dll.WintunReceivePacket
        self._receive_packet.argtypes = [pointer, ctypes.POINTER(ctypes.c_uint32)]
        self._receive_packet.restype = pointer
        self._release_packet = self._dll.WintunReleaseReceivePacket
        self._release_packet.argtypes = [pointer, pointer]
        self._release_packet.restype = None
        self._allocate_packet = self._dll.WintunAllocateSendPacket
        self._allocate_packet.argtypes = [pointer, ctypes.c_uint32]
        self._allocate_packet.restype = pointer
        self._send_packet = self._dll.WintunSendPacket
        self._send_packet.argtypes = [pointer, pointer]
        self._send_packet.restype = None
        self._get_read_wait_event = self._dll.WintunGetReadWaitEvent
        self._get_read_wait_event.argtypes = [pointer]
        self._get_read_wait_event.restype = pointer

    def read(self, size: int) -> bytes:
        while True:
            packet_size = ctypes.c_uint32()
            packet = self._receive_packet(self.session, ctypes.byref(packet_size))
            if packet:
                try:
                    return ctypes.string_at(packet, min(size, packet_size.value))
                finally:
                    self._release_packet(self.session, packet)
            error = ctypes.get_last_error()
            if error != self.ERROR_NO_MORE_ITEMS:
                raise ctypes.WinError(error)
            result = self._kernel32.WaitForSingleObject(self._wait_event, self.INFINITE)
            if result != self.WAIT_OBJECT_0:
                raise ctypes.WinError(ctypes.get_last_error())

    def write(self, packet: bytes) -> int:
        ptr = self._allocate_packet(self.session, len(packet))
        if not ptr:
            error = ctypes.get_last_error()
            if error == self.ERROR_BUFFER_OVERFLOW:
                return 0
            raise ctypes.WinError(error)
        if packet:
            ctypes.memmove(ptr, packet, len(packet))
        self._send_packet(self.session, ptr)
        return len(packet)

    def fileno(self) -> int:
        # This is a Windows event HANDLE. It is waitable with Win32 wait APIs,
        # but is not a POSIX descriptor and cannot be passed to select.select().
        return int(self._wait_event)

    def close(self) -> None:
        if getattr(self, "session", None):
            self._end_session(self.session)
            self.session = None
        if getattr(self, "adapter", None):
            self._close_adapter(self.adapter)
            self.adapter = None


class TapDevice:
    """Create and use a packet-oriented TUN device.

    Args:
        name: Requested interface name. macOS assigns ``utunN`` names itself.
        mode: ``IFF_TUN`` (default) or Linux-only ``IFF_TAP``.
        no_pi: Linux-only; omit the two-byte packet-information header.
        mtu: MTU to set when the interface is brought up.

    ``read`` and ``write`` exchange IP packets without platform headers.
    """

    def __init__(self, name: Optional[str] = None, mode: int = IFF_TUN,
                 no_pi: bool = True, mtu: int = _DEFAULT_MTU) -> None:
        self.mtu = mtu
        self.mode = mode
        self.no_pi = no_pi
        self._platform = platform.system()
        if self._platform == "Linux":
            self._backend = _LinuxBackend(name, mode, no_pi)
        elif self._platform == "Darwin":
            self._backend = _MacOSBackend(name, mode, no_pi)
        elif self._platform == "Windows":
            self._backend = _WindowsBackend(name, mode, no_pi)
        else:
            raise TapDeviceError(f"Unsupported operating system: {self._platform}")
        self.name = self._backend.name
        self._closed = False

    def fileno(self) -> int:
        """Return the POSIX file descriptor or Windows Wintun wait-event handle."""
        return self._backend.fileno()

    @property
    def fd(self) -> int:
        """Compatibility alias for ``fileno()``."""
        return self.fileno()

    def read(self, size: Optional[int] = None) -> bytes:
        """Read one packet; defaults to one MTU of payload."""
        if self._closed:
            raise ValueError("I/O operation on closed TUN device")
        if size is None:
            size = self.mtu
            if self._platform == "Linux" and not self.no_pi:
                size += 4
        return self._backend.read(size)

    def write(self, packet: bytes) -> int:
        """Write one complete IP packet to the interface."""
        if self._closed:
            raise ValueError("I/O operation on closed TUN device")
        if not isinstance(packet, (bytes, bytearray, memoryview)):
            raise TypeError("packet must be bytes-like")
        return self._backend.write(bytes(packet))

    def up(self) -> None:
        """Bring the interface up and apply the configured MTU."""
        if self._platform == "Windows":
            _run("netsh", "interface", "set", "interface", f"name={self.name}",
                 "admin=enabled")
            _run("netsh", "interface", "ipv4", "set", "subinterface",
                 self.name, f"mtu={self.mtu}", "store=active")
        else:
            _run("ifconfig", self.name, "mtu", str(self.mtu), "up")

    @staticmethod
    def _mac_peer(address: str, netmask: str) -> str:
        ip = ipaddress.ip_address(address)
        if ip.version == 4:
            network = ipaddress.ip_network(f"{address}/{netmask}", strict=False)
        else:
            network = ipaddress.ip_network(f"{address}/{netmask}", strict=False)
        for candidate in network.hosts():
            if candidate != ip:
                return str(candidate)
        raise ValueError(f"No other usable address in {network} for utun peer")

    def ifconfig(self, ip: Optional[str] = None, netmask: Optional[str] = None,
                 mtu: Optional[int] = None, peer: Optional[str] = None) -> None:
        """Configure interface addressing and/or MTU.

        For macOS, ``peer`` defaults to the first usable address in the given
        subnet other than ``ip``. This supplies utun's required point-to-point
        destination address. It is a deterministic placeholder, not a probe of
        address use on the network.
        """
        target_mtu = mtu if mtu is not None else self.mtu
        if self._platform == "Linux":
            args = ["ifconfig", self.name]
            if ip:
                args.append(ip)
                if netmask:
                    args.extend(["netmask", netmask])
            if target_mtu:
                args.extend(["mtu", str(target_mtu)])
            _run(*args)
        elif self._platform == "Darwin":
            if ip:
                if not netmask:
                    raise ValueError("netmask is required when configuring an IP")
                chosen_peer = peer or self._mac_peer(ip, netmask)
                args = ["ifconfig", self.name, "inet", ip, chosen_peer,
                        "netmask", netmask]
            else:
                args = ["ifconfig", self.name]
            if target_mtu:
                args.extend(["mtu", str(target_mtu)])
            _run(*args)
        else:
            if ip:
                if not netmask:
                    raise ValueError("netmask is required when configuring an IP")
                _run("netsh", "interface", "ipv4", "set", "address",
                     f"name={self.name}", "source=static", f"address={ip}",
                     f"mask={netmask}")
            if target_mtu:
                _run("netsh", "interface", "ipv4", "set", "subinterface",
                     self.name, f"mtu={target_mtu}", "store=active")
        if mtu is not None:
            self.mtu = mtu

    def close(self) -> None:
        if not self._closed:
            self._backend.close()
            self._closed = True

    def __enter__(self) -> "TapDevice":
        self.up()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


__all__ = ["TapDevice", "TapDeviceError", "IFF_TUN", "IFF_TAP", "IFF_NO_PI"]
