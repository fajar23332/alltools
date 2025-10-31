#!/usr/bin/env bash
# modules/setup-xray.sh — final version (auto config generate)
set -euo pipefail

if [ -f "$(dirname "$0")/../utils.sh" ]; then
  source "$(dirname "$0")/../utils.sh"
else
  echo_log(){ echo "[*] $*"; }
  err_log(){ echo "[!] $*" >&2; }
  run_sudo(){ if [ "$(id -u)" -eq 0 ]; then bash -c "$*"; else sudo bash -c "$*"; fi; }
fi

install_xray_manual(){
  local ver="1.9.11"
  local arch
  arch="$(uname -m)"
  case "$arch" in
    x86_64) arch="amd64" ;;
    aarch64) arch="arm64" ;;
    armv7l) arch="arm" ;;
    i686|i386) arch="386" ;;
    *) arch="amd64" ;;
  esac

  local tmp
  tmp="$(mktemp -d)"
  cd "$tmp"

  echo_log "[*] Installing Xray v$ver for $arch"

  local base="https://github.com/chaitin/xray/releases/download"
  local url1="$base/${ver}/xray_linux_${arch}.zip"
  local url2="$base/v${ver}/xray_linux_${arch}.zip"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o xray.zip "$url1" || curl -fsSL -o xray.zip "$url2"
  else
    wget -qO xray.zip "$url1" || wget -qO xray.zip "$url2"
  fi

  unzip -oq xray.zip
  local binfile
  binfile="$(find . -maxdepth 1 -type f -name 'xray*' | head -n1 || true)"
  [ -z "$binfile" ] && { err_log "Binary not found"; exit 1; }

  mv "$binfile" xray
  chmod +x xray

  echo_log "[*] Running Xray twice to generate configs..."
  ./xray >/dev/null 2>&1 || true
  ./xray >/dev/null 2>&1 || true

  echo_log "[*] Moving to /opt/xray..."
  run_sudo "mkdir -p /opt/xray"
  run_sudo "mv -f xray /opt/xray/xray"
  run_sudo "cp -rf ./*.yaml /opt/xray/" || true
  run_sudo "chmod +x /opt/xray/xray"

  echo_log "[*] Creating global wrapper..."
  run_sudo "tee /usr/local/bin/xray >/dev/null" <<'EOF'
#!/usr/bin/env bash
exec /opt/xray/xray "$@"
EOF
  run_sudo "chmod +x /usr/local/bin/xray"

  echo_log "[✅] Xray installed successfully at /opt/xray"
  echo_log "[ℹ️] Run: xray version"
  cd - >/dev/null
  rm -rf "$tmp"
}

if command -v xray >/dev/null 2>&1; then
  echo_log "[=] Xray already installed — skipping."
else
  install_xray_manual
fi
