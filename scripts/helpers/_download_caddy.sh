#!/usr/bin/env bash
set -euo pipefail

RUNTIME_ROOT="${AIVUDAOS_WS_ROOT:-${HOME}/aivudaOS_ws}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${RUNTIME_ROOT}/.tools/caddy"
FORCE="${FORCE:-0}"
SOURCE=""
OUTPUT="${INSTALL_DIR}/caddy"

usage() {
  cat <<EOF
Usage: $0 [--source SOURCE_PATH_OR_URL] [--output OUTPUT_PATH]

Options:
  --source, -s   Download source URL or local file path for caddy binary/archive
  --output, -o   Output path for installed caddy binary (default: ${OUTPUT})

Environment:
  FORCE=1        Reinstall even if output binary already exists
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --source|-s)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for $1" >&2
        usage >&2
        exit 1
      fi
      SOURCE="$2"
      shift 2
      ;;
    --output|-o)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for $1" >&2
        usage >&2
        exit 1
      fi
      OUTPUT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [[ -z "${SOURCE}" && "$#" -eq 1 ]]; then
        # Backward compatibility for previous positional source argument.
        SOURCE="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "${OUTPUT}" ]]; then
  echo "Output path cannot be empty." >&2
  exit 1
fi

if [[ -d "${OUTPUT}" || "${OUTPUT}" == */ ]]; then
  bin_path="${OUTPUT%/}/caddy"
else
  bin_path="${OUTPUT}"
fi

mkdir -p "$(dirname "${bin_path}")"

uname_s="$(uname -s | tr '[:upper:]' '[:lower:]')"
uname_m="$(uname -m | tr '[:upper:]' '[:lower:]')"

case "${uname_s}" in
  linux) os="linux" ;;
  darwin) os="darwin" ;;
  *)
    echo "Unsupported OS: ${uname_s}" >&2
    exit 1
    ;;
esac

case "${uname_m}" in
  x86_64|amd64) arch="amd64" ;;
  aarch64|arm64) arch="arm64" ;;
  *)
    echo "Unsupported architecture: ${uname_m}" >&2
    exit 1
    ;;
esac

if [[ -x "${bin_path}" && "${FORCE}" != "1" ]]; then
  echo "Caddy already installed: ${bin_path}"
  echo "Set FORCE=1 to reinstall."
  exit 0
fi

archive="$(dirname "${bin_path}")/caddy.tar.gz"
default_url="https://github.com/caddyserver/caddy/releases/latest/download/caddy_2_${os}_${arch}.tar.gz"

case "${os}/${arch}" in
  linux/amd64)
    download_url="https://caddyserver.com/api/download?os=linux&arch=amd64"
    ;;
  linux/arm64)
    download_url="https://caddyserver.com/api/download?os=linux&arch=arm64"
    ;;
  *)
    download_url="${default_url}"
    ;;
esac

install_from_archive() {
  local archive_path="$1"
  local tmp_dir

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  tar -xzf "${archive_path}" -C "${tmp_dir}"
  if [[ ! -f "${tmp_dir}/caddy" ]]; then
    echo "Archive does not contain caddy binary." >&2
    exit 1
  fi

  install -m 755 "${tmp_dir}/caddy" "${bin_path}"
}

install_from_binary() {
  local bin_source="$1"
  install -m 755 "${bin_source}" "${bin_path}"
}

if [[ -n "${SOURCE}" ]]; then
  if [[ "${SOURCE}" =~ ^https?:// ]]; then
    echo "Downloading Caddy from custom URL: ${SOURCE}"
    curl -fL "${SOURCE}" -o "${archive}"
    if tar -tzf "${archive}" >/dev/null 2>&1; then
      install_from_archive "${archive}"
    else
      install_from_binary "${archive}"
    fi
    rm -f "${archive}"
  else
    if [[ ! -f "${SOURCE}" ]]; then
      echo "Custom source file not found: ${SOURCE}" >&2
      exit 1
    fi

    echo "Installing Caddy from local source: ${SOURCE}"
    if tar -tzf "${SOURCE}" >/dev/null 2>&1; then
      install_from_archive "${SOURCE}"
    else
      install_from_binary "${SOURCE}"
    fi
  fi
else
  echo "Downloading Caddy from: ${download_url}"
  if [[ "${download_url}" == https://caddyserver.com/api/download* ]]; then
    curl -fL "${download_url}" -o "${bin_path}"
    chmod 755 "${bin_path}"
  else
    curl -fL "${download_url}" -o "${archive}"
    install_from_archive "${archive}"
    rm -f "${archive}"
  fi
fi

echo "Installed Caddy to: ${bin_path}"
"${bin_path}" version