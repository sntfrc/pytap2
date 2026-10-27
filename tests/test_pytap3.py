import errno
import os
import socket
import struct
import unittest
from unittest.mock import Mock, call, patch

from pytap3 import IFF_TUN, TapDevice, _MacOSBackend


class TestCase(unittest.TestCase):
    def test(self) -> None:
        pass


@unittest.skipIf(os.name == "nt", "the macOS backend requires fcntl")
class MacOSBackendTestCase(unittest.TestCase):
    def test_write_encodes_address_family_in_network_byte_order(self) -> None:
        backend = _MacOSBackend.__new__(_MacOSBackend)
        backend.sock = Mock()
        packet = b"\x45\x00"
        frame = struct.pack("!I", socket.AF_INET) + packet
        backend.sock.send.return_value = len(frame)

        self.assertEqual(backend.write(packet), len(packet))
        backend.sock.send.assert_called_once_with(frame)

    @patch("pytap3.fcntl.ioctl")
    @patch("pytap3.socket.socket")
    def test_automatic_name_uses_next_available_unit(
        self, socket_factory: Mock, _ioctl: Mock
    ) -> None:
        busy_socket = Mock()
        busy_socket.connect.side_effect = OSError(errno.EBUSY, "resource busy")
        available_socket = Mock()
        available_socket.getsockopt.return_value = b"utun1\0"
        socket_factory.side_effect = [busy_socket, available_socket]

        backend = _MacOSBackend(None, IFF_TUN, True)

        self.assertEqual(backend.name, "utun1")
        busy_socket.connect.assert_called_once_with((0, 1))
        available_socket.connect.assert_called_once_with((0, 2))
        busy_socket.close.assert_called_once_with()
        self.assertIs(backend.sock, available_socket)

    @patch("pytap3.fcntl.ioctl")
    @patch("pytap3.socket.socket")
    def test_requested_name_uses_exact_unit(
        self, socket_factory: Mock, _ioctl: Mock
    ) -> None:
        requested_socket = Mock()
        requested_socket.getsockopt.return_value = b"utun4\0"
        socket_factory.return_value = requested_socket

        backend = _MacOSBackend("utun4", IFF_TUN, True)

        self.assertEqual(backend.name, "utun4")
        requested_socket.connect.assert_called_once_with((0, 5))
        self.assertIs(backend.sock, requested_socket)

    @patch("pytap3.fcntl.ioctl")
    @patch("pytap3.socket.socket")
    def test_requested_busy_unit_retries_and_uses_assigned_name(
        self, socket_factory: Mock, _ioctl: Mock
    ) -> None:
        busy_socket = Mock()
        busy_socket.connect.side_effect = OSError(errno.EBUSY, "Resource busy")
        available_socket = Mock()
        available_socket.getsockopt.return_value = b"utun5\0"
        socket_factory.side_effect = [busy_socket, available_socket]

        backend = _MacOSBackend("utun4", IFF_TUN, True)

        self.assertEqual(backend.name, "utun5")
        busy_socket.connect.assert_called_once_with((0, 5))
        available_socket.connect.assert_called_once_with((0, 6))
        busy_socket.close.assert_called_once_with()
        self.assertIs(backend.sock, available_socket)


class MacOSRouteTestCase(unittest.TestCase):
    @patch("pytap3._run")
    def test_ifconfig_adds_route_for_configured_subnet(self, run: Mock) -> None:
        device = TapDevice.__new__(TapDevice)
        device._platform = "Darwin"
        device.name = "utun3"
        device.mtu = 1500

        device.ifconfig(ip="10.0.13.7", netmask="255.255.240.0")

        self.assertEqual(
            run.call_args_list,
            [
                call(
                    "ifconfig", "utun3", "inet", "10.0.13.7", "10.0.0.1",
                    "netmask", "255.255.240.0", "mtu", "1500",
                ),
                call(
                    "ifconfig", "utun3", "alias", "10.0.15.255",
                    "netmask", "255.255.240.0", "10.0.0.1", "up",
                ),
                call(
                    "route", "-n", "add", "-net", "10.0.0.0/20",
                    "-interface", "utun3",
                ),
            ],
        )

    @patch("pytap3._run")
    def test_ifconfig_without_address_does_not_add_route(self, run: Mock) -> None:
        device = TapDevice.__new__(TapDevice)
        device._platform = "Darwin"
        device.name = "utun3"
        device.mtu = 1500

        device.ifconfig(mtu=1400)

        run.assert_called_once_with("ifconfig", "utun3", "mtu", "1400")
