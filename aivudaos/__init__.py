from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    try:
        return version("aivudaos")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = get_version()
