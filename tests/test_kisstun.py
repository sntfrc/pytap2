from __future__ import annotations

import argparse
import ipaddress
import queue
import signal
import socket
import threading
import unittest
from typing import Optional
from unittest.mock import Mock, patch

from pytap3 import kisstun


class KISSTestCase(unittest.TestCase):
    def test_encode_escapes_kiss_special_bytes(self) -> None:
        packet = b"\x45\xc0\xdb\x00"

        self.assertEqual(
            kisstun._encode_kiss_frame(packet, 2),
            b"\xc0\x20\x45\xdb\xdc\xdb\xdd\x00\xc0",
        )

    def test_decoder_handles_split_frames_and_skips_other_commands(self) -> None:
        decoder = kisstun._KISSDecoder(port=0)

        self.assertEqual(decoder.feed(b"\xc0\x00one\xc0\x10other"), [b"one"])
        self.assertEqual(decoder.feed(b"\xc0\x00two\xc0"), [b"two"])

    def test_decoder_unescapes_special_bytes(self) -> None:
        decoder = kisstun._KISSDecoder(port=0)

        self.assertEqual(
            decoder.feed(b"\xc0\x00a\xdb\xdcb\xdb\xdd\xc0"),
            [b"a\xc0b\xdb"],
        )

    def test_bridge_forwards_packets_in_both_directions(self) -> None:
        class FakeDevice:
            def __init__(self) -> None:
                self.to_read: queue.Queue[Optional[bytes]] = queue.Queue()
                self.written: queue.Queue[bytes] = queue.Queue()

            def read(self) -> bytes:
                packet = self.to_read.get(timeout=2)
                if packet is None:
                    raise OSError("test device closed")
                return packet

            def write(self, packet: bytes) -> int:
                self.written.put(packet)
                return len(packet)

        device = FakeDevice()
        local, peer = socket.socketpair()
        errors: queue.Queue[ConnectionError] = queue.Queue()

        def run_bridge() -> None:
            try:
                kisstun._forward_packets(device, local, 0)
            except ConnectionError as exc:
                errors.put(exc)

        bridge = threading.Thread(target=run_bridge)
        bridge.start()
        inbound = b"\x45\x00from-tnc"
        outbound = b"\x45\x00from-tun"
        try:
            peer.sendall(kisstun._encode_kiss_frame(inbound, 0))
            self.assertEqual(device.written.get(timeout=2), inbound)

            device.to_read.put(outbound)
            expected = kisstun._encode_kiss_frame(outbound, 0)
            received = bytearray()
            while len(received) < len(expected):
                received.extend(peer.recv(len(expected) - len(received)))
            self.assertEqual(bytes(received), expected)
        finally:
            peer.close()
            bridge.join(timeout=2)
            device.to_read.put(None)
            local.close()

        self.assertFalse(bridge.is_alive())
        self.assertIsInstance(errors.get(timeout=1), ConnectionError)


class KISSTunArgumentsTestCase(unittest.TestCase):
    def test_ipv4_interface_requires_prefix(self) -> None:
        self.assertEqual(
            kisstun._ipv4_interface("44.61.0.1/28"),
            ipaddress.ip_interface("44.61.0.1/28"),
        )

        for value in ("44.61.0.1", "2001:db8::1/64", "not-an-address"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    kisstun._ipv4_interface(value)

    @patch("pytap3.kisstun._forward_packets")
    @patch("pytap3.kisstun.TapDevice")
    @patch("pytap3.kisstun.socket.create_connection")
    def test_main_configures_interface_and_starts_bridge(
        self, create_connection: Mock, tap_device: Mock, forward_packets: Mock
    ) -> None:
        connection = create_connection.return_value.__enter__.return_value
        device = tap_device.return_value.__enter__.return_value

        kisstun.main(["44.61.0.1/28"])

        create_connection.assert_called_once_with(("127.0.0.1", 8001), timeout=10)
        tap_device.assert_called_once_with(mtu=256)
        device.ifconfig.assert_called_once_with(
            ip="44.61.0.1",
            netmask="255.255.255.240",
            mtu=256,
        )
        forward_packets.assert_called_once_with(device, connection, 0)

    def test_help_uses_compact_kiss_port_range_and_shows_endpoint_default(self) -> None:
        with patch("sys.stdout") as output:
            with self.assertRaises(SystemExit) as raised:
                kisstun._build_parser().parse_args(["--help"])
        self.assertEqual(raised.exception.code, 0)
        help_text = "".join(str(call.args[0]) for call in output.write.call_args_list)
        self.assertIn("--kiss-port 0-15", help_text)
        self.assertNotIn("{0,1,2,3", help_text)
        self.assertIn("127.0.0.1:8001", help_text)

    @patch("pytap3.kisstun._wait_for_tcp_listener")
    @patch("pytap3.kisstun.subprocess.Popen")
    def test_direwolf_is_started_waited_for_and_terminated(
        self, popen: Mock, wait_for_listener: Mock
    ) -> None:
        process = popen.return_value
        process.poll.return_value = None

        with kisstun._managed_direwolf(True, "127.0.0.1", 8001):
            popen.assert_called_once_with(["direwolf"])
            wait_for_listener.assert_called_once_with(
                process, "127.0.0.1", 8001, kisstun._DIREWOLF_STARTUP_TIMEOUT
            )
            process.terminate.assert_not_called()

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)

    @patch("pytap3.kisstun._wait_for_tcp_listener", side_effect=TimeoutError("no listener"))
    @patch("pytap3.kisstun.subprocess.Popen")
    def test_direwolf_is_terminated_if_listener_never_starts(
        self, popen: Mock, wait_for_listener: Mock
    ) -> None:
        process = popen.return_value
        process.poll.return_value = None

        with self.assertRaisesRegex(TimeoutError, "no listener"):
            with kisstun._managed_direwolf(True, "127.0.0.1", 8001):
                pass

        wait_for_listener.assert_called_once()
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)

    @patch("pytap3.kisstun._wait_for_tcp_listener")
    @patch("pytap3.kisstun.subprocess.Popen")
    def test_direwolf_is_terminated_on_sigterm(
        self, popen: Mock, wait_for_listener: Mock
    ) -> None:
        process = popen.return_value
        process.poll.return_value = None

        with self.assertRaises(SystemExit) as raised:
            with kisstun._managed_direwolf(True, "127.0.0.1", 8001):
                signal.raise_signal(signal.SIGTERM)

        wait_for_listener.assert_called_once()
        self.assertEqual(raised.exception.code, 128 + signal.SIGTERM)
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)
