import hashlib
import io
from pathlib import Path
import sys
import sysconfig
from typing import Dict, List, Tuple, cast
import urllib.request
import zipfile

from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel

WINTUN_URL = "https://www.wintun.net/builds/wintun-0.14.1.zip"
WINTUN_SHA256 = "07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51"

_PLATFORM_ARCHITECTURES: Dict[str, str] = {
    "win32": "x86",
    "win-amd64": "amd64",
    "win-arm32": "arm",
    "win-arm64": "arm64",
}


def get_wintun_architecture() -> str:
    platform_name = sysconfig.get_platform().lower()
    try:
        return _PLATFORM_ARCHITECTURES[platform_name]
    except KeyError as exc:
        raise RuntimeError(
            "Unsupported Windows platform for Wintun: {}".format(platform_name)
        ) from exc


def download_wintun(destination: Path, architecture: str) -> None:
    with urllib.request.urlopen(WINTUN_URL, timeout=30) as response:
        archive_data = response.read()
    digest = hashlib.sha256(archive_data).hexdigest()
    if digest != WINTUN_SHA256:
        raise ValueError(
            "Wintun archive SHA-256 mismatch: expected {}, got {}".format(WINTUN_SHA256, digest)
        )

    member_name = "wintun/bin/{}/wintun.dll".format(architecture)
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(member_name))
        (destination.parent / "wintun-LICENSE.txt").write_bytes(archive.read("wintun/LICENSE.txt"))


class WintunBuildPy(build_py):  # type: ignore[misc]
    def get_outputs(self, include_bytecode: int = 1) -> List[str]:
        outputs = cast(List[str], super().get_outputs(include_bytecode))
        if sys.platform == "win32":
            package_directory = Path(self.build_lib) / "pytap3"
            outputs.extend(
                str(package_directory / filename)
                for filename in ("wintun.dll", "wintun-LICENSE.txt")
            )
        return outputs

    def run(self) -> None:
        super().run()
        if sys.platform == "win32":
            architecture = get_wintun_architecture()
            destination = Path(self.build_lib) / "pytap3" / "wintun.dll"
            download_wintun(destination, architecture)


class PlatformWheel(bdist_wheel):  # type: ignore[misc]
    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> Tuple[str, str, str]:
        _, _, platform_tag = cast(Tuple[str, str, str], super().get_tag())
        return "py3", "none", platform_tag
