#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${REPO_DIR}/.tools/caddy"
FORCE="${FORCE:-0}"

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

mkdir -p "${INSTALL_DIR}"

bin_path="${INSTALL_DIR}/caddy"
if [[ -x "${bin_path}" && "${FORCE}" != "1" ]]; then
  echo "Caddy already installed: ${bin_path}"
  echo "Set FORCE=1 to reinstall."
  exit 0
fi

archive="${INSTALL_DIR}/caddy.tar.gz"
default_url="https://github.com/caddyserver/caddy/releases/latest/download/caddy_2_${os}_${arch}.tar.gz"

resolve_release_url() {
  local api_url
  api_url="https://api.github.com/repos/caddyserver/caddy/releases/latest"
  curl -fsSL "${api_url}" \
    | grep -Eo 'https://[^"[:space:]]+/caddy_[^"[:space:]]+_'"${os}"'_'"${arch}"'\.tar\.gz' \
    | head -n 1
}

download_url="${default_url}"
echo "Downloading Caddy from: ${download_url}"
if ! curl -fL "${download_url}" -o "${archive}"; then
  echo "Default URL failed, resolving latest release asset URL from GitHub API..."
  download_url="$(resolve_release_url || true)"
  if [[ -z "${download_url}" ]]; then
    echo "Failed to resolve latest Caddy release URL for ${os}/${arch}." >&2
    exit 1
  fi
  echo "Downloading Caddy from: ${download_url}"
  curl -fL "${download_url}" -o "${archive}"
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

tar -xzf "${archive}" -C "${tmp_dir}"
if [[ ! -f "${tmp_dir}/caddy" ]]; then
  echo "Downloaded archive does not contain caddy binary." >&2
  exit 1
fi

install -m 755 "${tmp_dir}/caddy" "${bin_path}"
rm -f "${archive}"

echo "Installed Caddy to: ${bin_path}"
"${bin_path}" version