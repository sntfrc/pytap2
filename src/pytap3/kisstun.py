"""Bridge an IPv4 TUN interface to a TCP-connected KISS TNC."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ipaddress
import queue
import signal
import socket
import subprocess
import threading
import time
from typing import Generator, List, Optional, Protocol

from pytap3 import TapDevice


class _PacketDevice(Protocol):
    def read(self) -> bytes:
        ...

    def write(self, packet: bytes) -> int:
        ...


_FEND = 0xC0
_FESC = 0xDB
_TFEND = 0xDC
_TFESC = 0xDD
_MAX_KISS_FRAME_SIZE = 65536
_DIREWOLF_STARTUP_TIMEOUT = 30
_DISCOVERY_UDP_PORTS = frozenset((67, 68, 137, 138, 1900, 3702, 5353, 5355))


class _KISSDecoder:
    def __init__(self, port: int) -> None:
        self.port = port
        self._in_frame = False
        self._escaped = False
        self._frame = bytearray()

    def feed(self, data: bytes) -> List[bytes]:
        packets = []
        for value in data:
            if value == _FEND:
                if self._in_frame and not self._escaped and len(self._frame) > 1:
                    command = self._frame[0]
                    if command >> 4 == self.port and command & 0x0F == 0:
                        packets.append(bytes(self._frame[1:]))
                self._frame.clear()
                self._escaped = False
                self._in_frame = True
                continue

            if not self._in_frame:
                continue

            if self._escaped:
                if value == _TFEND:
                    self._frame.append(_FEND)
                elif value == _TFESC:
                    self._frame.append(_FESC)
                else:
                    self._frame.clear()
                    self._in_frame = False
                self._escaped = False
            elif value == _FESC:
                self._escaped = True
            else:
                self._frame.append(value)

            if len(self._frame) > _MAX_KISS_FRAME_SIZE:
                self._frame.clear()
                self._in_frame = False
                self._escaped = False

        return packets


def _encode_kiss_frame(packet: bytes, port: int) -> bytes:
    frame = bytearray((port << 4,))
    for value in packet:
        if value == _FEND:
            frame.extend((_FESC, _TFEND))
        elif value == _FESC:
            frame.extend((_FESC, _TFESC))
        else:
            frame.append(value)
    return bytes((_FEND,)) + bytes(frame) + bytes((_FEND,))


def _is_forwardable_ipv4_packet(
    packet: bytes, network: ipaddress.IPv4Network
) -> bool:
    if len(packet) < 20 or packet[0] >> 4 != 4:
        return False

    header_length = (packet[0] & 0x0F) * 4
    if header_length < 20 or len(packet) < header_length:
        return False

    total_length = int.from_bytes(packet[2:4], "big")
    if total_length < header_length or total_length > len(packet):
        return False

    destination = ipaddress.IPv4Address(packet[16:20])
    if destination.is_multicast or destination.is_unspecified:
        return False

    if packet[9] == socket.IPPROTO_UDP and total_length >= header_length + 8:
        fragment_offset = int.from_bytes(packet[6:8], "big") & 0x1FFF
        if fragment_offset == 0:
            source_port = int.from_bytes(packet[header_length : header_length + 2], "big")
            destination_port = int.from_bytes(packet[header_length + 2 : header_length + 4], "big")
            if (
                source_port in _DISCOVERY_UDP_PORTS
                or destination_port in _DISCOVERY_UDP_PORTS
            ):
                return False

    if destination == network.broadcast_address:
        return True

    return not (
        destination.is_reserved
        or destination.is_loopback
        or destination.is_link_local
    )


def _forward_packets(
    device: _PacketDevice,
    connection: socket.socket,
    port: int,
    network: ipaddress.IPv4Network,
    filter_outgoing: bool = True,
) -> None:
    stop = threading.Event()
    sender_errors: queue.Queue[OSError] = queue.Queue()

    def send_tun_packets() -> None:
        try:
            while not stop.is_set():
                packet = device.read()
                if packet and (
                    not filter_outgoing or _is_forwardable_ipv4_packet(packet, network)
                ):
                    connection.sendall(_encode_kiss_frame(packet, port))
        except OSError as exc:
            if not stop.is_set():
                sender_errors.put(exc)
                stop.set()
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    connection.settimeout(0.5)
    sender = threading.Thread(target=send_tun_packets, daemon=True)
    sender.start()
    decoder = _KISSDecoder(port)

    try:
        while True:
            try:
                data = connection.recv(4096)
            except socket.timeout:
                if not sender_errors.empty():
                    raise sender_errors.get()
                continue
            except OSError:
                if not sender_errors.empty():
                    raise sender_errors.get()
                raise

            if not data:
                if not sender_errors.empty():
                    raise sender_errors.get()
                raise ConnectionError("TCP KISS TNC closed the connection")
            for packet in decoder.feed(data):
                device.write(packet)
    finally:
        stop.set()
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sender.join(timeout=1)


def _ipv4_interface(value: str) -> ipaddress.IPv4Interface:
    try:
        interface = ipaddress.ip_interface(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not isinstance(interface, ipaddress.IPv4Interface):
        raise argparse.ArgumentTypeError("kisstun currently supports IPv4 addresses only")
    if "/" not in value:
        raise argparse.ArgumentTypeError("address must include a prefix length, e.g. 10.73.0.1/16")
    return interface


def _wait_for_tcp_listener(
    process: subprocess.Popen[bytes], host: str, port: int, timeout: int
) -> None:
    deadline = time.monotonic() + timeout
    last_error: Optional[OSError] = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Dire Wolf exited with status {process.returncode} before "
                f"opening {host}:{port}"
            )
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    detail = f": {last_error}" if last_error is not None else ""
    raise TimeoutError(
        f"Timed out waiting for Dire Wolf to listen on {host}:{port}{detail}"
    )


@contextmanager
def _managed_direwolf(enabled: bool, host: str, port: int) -> Generator[None, None, None]:
    if not enabled:
        yield
        return

    previous_handler = signal.getsignal(signal.SIGTERM)

    def handle_sigterm(signum: int, frame: object) -> None:
        del frame
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_sigterm)
    process: Optional[subprocess.Popen[bytes]] = None
    try:
        try:
            process = subprocess.Popen(["direwolf"])
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Could not launch Dire Wolf; ensure 'direwolf' is installed and on PATH"
            ) from exc
        _wait_for_tcp_listener(process, host, port, _DIREWOLF_STARTUP_TIMEOUT)
        yield
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    process.wait()
        finally:
            signal.signal(signal.SIGTERM, previous_handler)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kisstun",
        description=(
            "Bridge a TUN interface to a TCP KISS TNC. "
            "Default TCP KISS endpoint: 127.0.0.1:8001."
        ),
    )
    parser.add_argument(
        "address",
        type=_ipv4_interface,
        help="IPv4 interface address and prefix length, e.g. 10.73.0.1/16",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="TCP KISS TNC host (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="TCP KISS TNC port (default: %(default)s)",
    )
    parser.add_argument(
        "--kiss-port",
        type=int,
        choices=range(16),
        metavar="0-15",
        default=0,
        help="KISS hardware port number (default: %(default)s)",
    )
    parser.add_argument(
        "--direwolf",
        action="store_true",
        help="launch Dire Wolf and wait for its TCP KISS listener",
    )
    parser.add_argument(
        "--no-filter",
        dest="filter_outgoing",
        action="store_false",
        default=True,
        help="disable outgoing IPv4 packet filtering (enabled by default)",
    )
    parser.add_argument(
        "--mtu",
        type=int,
        default=256,
        help="TUN interface MTU (default: %(default)s)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.port < 1 or args.port > 65535:
        parser.error("--port must be between 1 and 65535")
    if args.mtu < 1 or args.mtu > 65535:
        parser.error("--mtu must be between 1 and 65535")

    with _managed_direwolf(args.direwolf, args.host, args.port):
        with socket.create_connection((args.host, args.port), timeout=10) as connection:
            with TapDevice(mtu=args.mtu) as device:
                device.ifconfig(
                    ip=str(args.address.ip),
                    netmask=str(args.address.network.netmask),
                    mtu=args.mtu,
                )
                print(
                    f"Bridging {args.address} on {device.name} to "
                    f"{args.host}:{args.port} (KISS port {args.kiss_port})",
                    flush=True,
                )
                _forward_packets(
                    device,
                    connection,
                    args.kiss_port,
                    args.address.network,
                    args.filter_outgoing,
                )


if __name__ == "__main__":
    main()
