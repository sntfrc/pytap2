import errno
import os
import unittest
from unittest.mock import Mock, patch

from pytap2 import IFF_TUN, TapDevice, _MacOSBackend


class TestCase(unittest.TestCase):
    def test(self) -> None:
        pass


@unittest.skipIf(os.name == "nt", "the macOS backend requires fcntl")
class MacOSBackendTestCase(unittest.TestCase):
    @patch("pytap2.fcntl.ioctl")
    @patch("pytap2.socket.socket")
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

    @patch("pytap2.fcntl.ioctl")
    @patch("pytap2.socket.socket")
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

    @patch("pytap2.fcntl.ioctl")
    @patch("pytap2.socket.socket")
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
