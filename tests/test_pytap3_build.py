import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import pytap3_build
from setuptools import Distribution


def _wintun_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("wintun/LICENSE.txt", "Wintun license")
        for architecture in ("x86", "amd64", "arm", "arm64"):
            archive.writestr("wintun/bin/{}/wintun.dll".format(architecture), architecture)
    return buffer.getvalue()


class WintunBuildTestCase(unittest.TestCase):
    def test_architecture_matches_windows_python_platform(self) -> None:
        for platform_name, expected in (
            ("win32", "x86"),
            ("win-amd64", "amd64"),
            ("win-arm32", "arm"),
            ("win-arm64", "arm64"),
        ):
            with self.subTest(platform=platform_name):
                with patch(
                    "pytap3_build.sysconfig.get_platform",
                    return_value=platform_name,
                ):
                    self.assertEqual(pytap3_build.get_wintun_architecture(), expected)

    def test_unsupported_platform_is_reported(self) -> None:
        with patch("pytap3_build.sysconfig.get_platform", return_value="win-unknown"):
            with self.assertRaisesRegex(RuntimeError, "win-unknown"):
                pytap3_build.get_wintun_architecture()

    def test_download_extracts_matching_dll_and_license(self) -> None:
        archive_data = _wintun_archive()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "pytap3" / "wintun.dll"
            with patch(
                "pytap3_build.urllib.request.urlopen",
                return_value=io.BytesIO(archive_data),
            ) as urlopen:
                with patch.object(
                    pytap3_build,
                    "WINTUN_SHA256",
                    hashlib.sha256(archive_data).hexdigest(),
                ):
                    pytap3_build.download_wintun(destination, "arm64")

            urlopen.assert_called_once_with(pytap3_build.WINTUN_URL, timeout=30)
            self.assertEqual(destination.read_bytes(), b"arm64")
            self.assertEqual(
                (destination.parent / "wintun-LICENSE.txt").read_bytes(),
                b"Wintun license",
            )

    def test_download_rejects_unexpected_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "pytap3" / "wintun.dll"
            with patch(
                "pytap3_build.urllib.request.urlopen",
                return_value=io.BytesIO(b"not the official archive"),
            ):
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    pytap3_build.download_wintun(destination, "amd64")
            self.assertFalse(destination.exists())

    def test_windows_build_includes_downloaded_files_as_outputs(self) -> None:
        command = pytap3_build.WintunBuildPy(Distribution({"packages": []}))
        command.ensure_finalized()
        with tempfile.TemporaryDirectory() as directory:
            command.build_lib = directory
            with patch("pytap3_build.sys.platform", "win32"):
                with patch("pytap3_build.build_py.run"):
                    with patch("pytap3_build.get_wintun_architecture", return_value="amd64"):
                        with patch("pytap3_build.download_wintun") as download:
                            command.run()
                            download.assert_called_once_with(
                                Path(directory) / "pytap3" / "wintun.dll", "amd64"
                            )
                            outputs = command.get_outputs()
                            self.assertIn(
                                str(Path(directory) / "pytap3" / "wintun.dll"),
                                outputs,
                            )
                            self.assertIn(
                                str(Path(directory) / "pytap3" / "wintun-LICENSE.txt"),
                                outputs,
                            )

    def test_wheel_uses_platform_tag_without_python_abi_tag(self) -> None:
        command = pytap3_build.PlatformWheel(Distribution())
        with patch("pytap3_build.bdist_wheel.finalize_options"):
            command.finalize_options()
        self.assertFalse(command.root_is_pure)

        with patch(
            "pytap3_build.bdist_wheel.get_tag",
            return_value=("cp315", "cp315", "win_amd64"),
        ):
            self.assertEqual(command.get_tag(), ("py3", "none", "win_amd64"))
