#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}" && pwd)"

BUILD_SEQ="${AIVUDAOS_BUILD_SEQ:-01}"
BUILD_DATE="${AIVUDAOS_BUILD_DATE:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PUBLISH_VENV_DIR="${PUBLISH_VENV_DIR:-${REPO_DIR}/.publish-venv}"
PUBLISH_TOOLS_DIR="${PUBLISH_TOOLS_DIR:-${REPO_DIR}/.publish-tools}"
SKIP_UPLOAD=0
NO_ISOLATION=0
REPOSITORY=""
REPOSITORY_URL=""

usage() {
  cat <<EOF
Usage: $0 [options]

Build AivudaOS wheel/sdist and upload them to PyPI with twine.

Options:
  --skip-upload            Build and run twine check, but do not upload.
  --no-isolation           Pass --no-isolation to python -m build.
  --repository NAME        Twine repository name, for example: pypi or testpypi.
  --repository-url URL     Explicit twine repository URL.
  --python BIN             Python executable to use. Default: ${PYTHON_BIN}
  --venv-dir PATH          Virtualenv path for isolated build/twine tools.
  --tools-dir PATH         Fallback target dir for isolated build/twine tools.
  --build-date YYYYMMDD    Override AIVUDAOS_BUILD_DATE.
  --build-seq NN           Override AIVUDAOS_BUILD_SEQ. Default: ${BUILD_SEQ}
  -h, --help               Show this help.
  -V, --version            Print the current package version metadata if available.

Environment:
  AIVUDAOS_BUILD_DATE      Build date used in version suffix.
  AIVUDAOS_BUILD_SEQ       Build sequence used in version suffix.
  PUBLISH_VENV_DIR         Virtualenv path used for build/twine isolation.
  PUBLISH_TOOLS_DIR        Fallback pip --target dir used when venv is unavailable.
  TWINE_USERNAME           Twine username. Use __token__ for API token auth.
  TWINE_PASSWORD           Twine password or API token value.
  TWINE_NON_INTERACTIVE=1  Recommended for CI.

Examples:
  AIVUDAOS_BUILD_SEQ=03 TWINE_USERNAME=__token__ TWINE_PASSWORD=... $0
  AIVUDAOS_BUILD_SEQ=03 $0 --skip-upload --no-isolation
  AIVUDAOS_BUILD_SEQ=03 $0 --repository testpypi
EOF
}

print_version() {
  local package_version="unknown"
  package_version="$(
    REPO_DIR="${REPO_DIR}" PYTHONPATH="${REPO_DIR}" "${PYTHON_BIN}" - <<'PY' 2>/dev/null || true
import os
from pathlib import Path
ns = {"__file__": str(Path(os.environ["REPO_DIR"]) / "setup.py")}
setup_path = Path(os.environ["REPO_DIR"]) / "setup.py"
code = setup_path.read_text(encoding="utf-8")
prefix = code.split("\nsetup(", 1)[0]
exec(prefix, ns)
print(ns["build_version"]())
PY
  )"
  echo "${package_version}"
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command not found: ${command_name}" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-upload)
      SKIP_UPLOAD=1
      shift
      ;;
    --no-isolation)
      NO_ISOLATION=1
      shift
      ;;
    --repository)
      REPOSITORY="${2:-}"
      shift 2
      ;;
    --repository-url)
      REPOSITORY_URL="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --venv-dir)
      PUBLISH_VENV_DIR="${2:-}"
      shift 2
      ;;
    --tools-dir)
      PUBLISH_TOOLS_DIR="${2:-}"
      shift 2
      ;;
    --build-date)
      BUILD_DATE="${2:-}"
      shift 2
      ;;
    --build-seq)
      BUILD_SEQ="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -V|--version)
      print_version
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_command "${PYTHON_BIN}"
require_command npm

if [[ -n "${BUILD_DATE}" && ! "${BUILD_DATE}" =~ ^[0-9]{8}$ ]]; then
  echo "Invalid --build-date value: ${BUILD_DATE}" >&2
  exit 1
fi

if [[ ! "${BUILD_SEQ}" =~ ^[0-9]+$ ]]; then
  echo "Invalid --build-seq value: ${BUILD_SEQ}" >&2
  exit 1
fi

cd "${REPO_DIR}"

echo "[publish_aivudaos_pypi] Cleaning dist/ build/ aivudaos.egg-info/ ..."
rm -rf dist build aivudaos.egg-info
rm -rf "${PUBLISH_VENV_DIR}" "${PUBLISH_TOOLS_DIR}"

RUN_PYTHON=()
if "${PYTHON_BIN}" -m venv "${PUBLISH_VENV_DIR}" >/dev/null 2>&1; then
  echo "[publish_aivudaos_pypi] Using isolated virtualenv at ${PUBLISH_VENV_DIR} ..."
  VENV_PYTHON="${PUBLISH_VENV_DIR}/bin/python"
  VENV_PIP="${PUBLISH_VENV_DIR}/bin/pip"
  echo "[publish_aivudaos_pypi] Installing build/twine into isolated virtualenv ..."
  "${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel
  "${VENV_PIP}" install --upgrade build twine
  RUN_PYTHON=("${VENV_PYTHON}")
else
  echo "[publish_aivudaos_pypi] python -m venv is unavailable; falling back to isolated pip --target tools dir at ${PUBLISH_TOOLS_DIR} ..."
  mkdir -p "${PUBLISH_TOOLS_DIR}"
  "${PYTHON_BIN}" -m pip install --upgrade --target "${PUBLISH_TOOLS_DIR}" pip setuptools wheel build twine
  RUN_PYTHON=("${PYTHON_BIN}")
fi

echo "[publish_aivudaos_pypi] Building ui/dist ..."
(
  cd aivudaos/resources/ui
  npm install
  npm run build
)

BUILD_ARGS=()
if [[ "${NO_ISOLATION}" -eq 1 ]]; then
  BUILD_ARGS+=(--no-isolation)
fi

echo "[publish_aivudaos_pypi] Building Python distributions ..."
AIVUDAOS_BUILD_SEQ="${BUILD_SEQ}" \
AIVUDAOS_BUILD_DATE="${BUILD_DATE}" \
  PYTHONPATH="${PUBLISH_TOOLS_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${RUN_PYTHON[@]}" -m build "${BUILD_ARGS[@]}"

echo "[publish_aivudaos_pypi] Running twine check ..."
PYTHONPATH="${PUBLISH_TOOLS_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${RUN_PYTHON[@]}" -m twine check dist/*

if [[ "${SKIP_UPLOAD}" -eq 1 ]]; then
  echo "[publish_aivudaos_pypi] Skip upload enabled. Built artifacts:"
  ls -1 dist
  exit 0
fi

TWINE_ARGS=()
if [[ -n "${REPOSITORY}" ]]; then
  TWINE_ARGS+=(--repository "${REPOSITORY}")
fi
if [[ -n "${REPOSITORY_URL}" ]]; then
  TWINE_ARGS+=(--repository-url "${REPOSITORY_URL}")
fi

echo "[publish_aivudaos_pypi] Uploading with twine ..."
PYTHONPATH="${PUBLISH_TOOLS_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${RUN_PYTHON[@]}" -m twine upload "${TWINE_ARGS[@]}" dist/*

echo "[publish_aivudaos_pypi] Publish complete."
