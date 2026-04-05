from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT
BASE_VERSION = "1.0.0"


def build_version() -> str:
    build_date = os.environ.get("AIVUDAOS_BUILD_DATE", "").strip()
    if not build_date:
      build_date = datetime.now().strftime("%Y%m%d")

    build_seq = os.environ.get("AIVUDAOS_BUILD_SEQ", "01").strip() or "01"
    if not build_date.isdigit() or len(build_date) != 8:
        raise RuntimeError(f"Invalid AIVUDAOS_BUILD_DATE: {build_date!r}")
    if not build_seq.isdigit():
        raise RuntimeError(f"Invalid AIVUDAOS_BUILD_SEQ: {build_seq!r}")

    build_seq = build_seq.zfill(2)
    return f"{BASE_VERSION}.dev{build_date}{build_seq}"


def read_requirements() -> list[str]:
    requirements_path = SOURCE_ROOT / "requirements.txt"
    requirements: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirements.append(stripped)
    return requirements


def ensure_ui_dist() -> None:
    ui_dir = SOURCE_ROOT / "ui"
    package_json = ui_dir / "package.json"
    dist_dir = ui_dir / "dist"

    if not package_json.exists():
        if dist_dir.exists():
            return
        raise RuntimeError(f"UI package.json not found: {package_json}")

    npm_cmd = shutil.which("npm")
    if npm_cmd is None:
        raise RuntimeError("npm is required to build ui/dist before packaging")

    subprocess.run([npm_cmd, "run", "build"], cwd=ui_dir, check=True)


class build_py(_build_py):
    def run(self) -> None:
        ensure_ui_dist()
        super().run()
        self._copy_packaged_resources()

    def _copy_packaged_resources(self) -> None:
        destination_root = Path(self.build_lib) / "aivudaos" / "resources"
        resource_specs = [
            ("Caddyfile_template", "Caddyfile_template"),
            ("README.md", "README.md"),
            ("requirements.txt", "requirements.txt"),
            ("scripts", "scripts"),
            ("ui/dist", "ui/dist"),
        ]

        for source_rel, dest_rel in resource_specs:
            source_path = SOURCE_ROOT / source_rel
            destination_path = destination_root / dest_rel
            if not source_path.exists():
                raise RuntimeError(f"Required packaging resource not found: {source_path}")

            if source_path.is_dir():
                if destination_path.exists():
                    shutil.rmtree(destination_path)
                shutil.copytree(source_path, destination_path)
            else:
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_path)


class sdist(_sdist):
    def run(self) -> None:
        ensure_ui_dist()
        super().run()


setup(
    name="aivudaos",
    version=build_version(),
    description="AivudaOS packaged for pip installation and PyPI publishing.",
    long_description=(SOURCE_ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    package_dir={"": "."},
    packages=find_packages(where="."),
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={"console_scripts": ["aivudaos=aivudaos.cli:main"]},
    cmdclass={"build_py": build_py, "sdist": sdist},
    package_data={"aivudaos": ["resources/*", "resources/**/*"]},
)
