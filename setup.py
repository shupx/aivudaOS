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
SDIST_EXCLUDED_PATHS = (
    Path("aivudaos/resources/ui/node_modules"),
    Path("aivudaos/resources/ui/dist"),
    Path("aivudaos/resources/ui/.vite"),
    Path("aivudaos/resources/ui/.vite-temp"),
)


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _should_exclude_from_sdist(path: Path) -> bool:
    normalized = Path(*path.parts)
    for excluded in SDIST_EXCLUDED_PATHS:
        if normalized == excluded or _is_relative_to(normalized, excluded):
            return True
    return False


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
    ui_dir = SOURCE_ROOT / "aivudaos" / "resources" / "ui"
    package_json = ui_dir / "package.json"
    dist_dir = SOURCE_ROOT / "aivudaos" / "resources" / "ui" / "dist"

    if not package_json.exists():
        if dist_dir.exists():
            return
        raise RuntimeError(f"UI package.json not found: {package_json}")

    npm_cmd = shutil.which("npm")
    if npm_cmd is None:
        raise RuntimeError("npm is required to build aivudaos/resources/ui/dist before packaging")

    subprocess.run([npm_cmd, "install"], cwd=ui_dir, check=True)
    subprocess.run([npm_cmd, "run", "build"], cwd=ui_dir, check=True)


class build_py(_build_py):
    def run(self) -> None:
        ensure_ui_dist()
        super().run()
        self._copy_packaged_resources()

    def _copy_packaged_resources(self) -> None:
        source_path = SOURCE_ROOT / "aivudaos" / "resources"
        destination_path = Path(self.build_lib) / "aivudaos" / "resources"
        if not source_path.exists():
            raise RuntimeError(f"Required packaging resource not found: {source_path}")
        if destination_path.exists():
            shutil.rmtree(destination_path)
        shutil.copytree(
            source_path,
            destination_path,
            ignore=self._ignore_packaged_resources,
        )

    @staticmethod
    def _ignore_packaged_resources(directory: str, entries: list[str]) -> list[str]:
        current = Path(directory)
        ignored = {name for name in entries if name in {"node_modules", ".vite", ".vite-temp"}}

        if current.name == "ui":
            ignored.update(
                name
                for name in entries
                if name != "dist"
            )

        return sorted(ignored)


class sdist(_sdist):
    def run(self) -> None:
        ensure_ui_dist()
        super().run()

    def make_release_tree(self, base_dir: str, files: list[str]) -> None:
        filtered_files = [
            file_path
            for file_path in files
            if not _should_exclude_from_sdist(Path(file_path))
        ]
        super().make_release_tree(base_dir, filtered_files)
        self._prune_release_tree(Path(base_dir))

    def _prune_release_tree(self, base_dir: Path) -> None:
        for excluded in SDIST_EXCLUDED_PATHS:
            target = base_dir / excluded
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()


setup(
    name="aivudaos",
    version=build_version(),
    description="AivudaOS packaged for pip installation and PyPI publishing.",
    long_description=(SOURCE_ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    python_requires=">=3.8",
    package_dir={"": "."},
    packages=find_packages(where=".", include=["aivudaos", "aivudaos.*"]),
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={"console_scripts": ["aivudaos=aivudaos.cli:main"]},
    cmdclass={"build_py": build_py, "sdist": sdist},
    package_data={"aivudaos": ["resources/*", "resources/**/*"]},
)
