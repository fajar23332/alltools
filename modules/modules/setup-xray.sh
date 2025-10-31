#!/usr/bin/env bash
# modules/setup-apt.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

install_xray_manual(){
  ver="1.9.11"
  tmp="$(mktemp -d)"
  cd "$tmp" || return 1
  echo_log "Downloading xray v$ver..."
  url="https://github.com/chaitin/xray/releases/download/v${ver}/xray_linux_amd64.zip"
  curl -sL -o xray.zip "$url" || { err_log "download xray failed"; return 1; }
  unzip -o xray.zip >>"$LOGFILE" 2>&1 || true
  # move/rename per instruksi
  if [ -f xray_linux_amd64 ]; then
    mv xray_linux_amd64 xray || true
  fi
  chmod +x xray || true
  # run twice to generate config
  ./xray >/dev/null 2>&1 || true
  ./xray >/dev/null 2>&1 || true
  run_sudo "mv -f xray /usr/local/bin/xray" || mv -f xray /usr/local/bin/xray
  # copy configs if created
  if [ -d ./configs ]; then
    run_sudo "mkdir -p /usr/local/share/xray-configs"
    run_sudo "cp -r ./configs/* /usr/local/share/xray-configs/" || true
  fi
  echo_log "xray installed to /usr/local/bin/xray"
  cd - >/dev/null 2>&1 || true
  rm -rf "$tmp"
}

# call if xray not installed
if ! command -v xray >/dev/null 2>&1; then
  install_xray_manual
else
  echo_log "xray present"
fi
