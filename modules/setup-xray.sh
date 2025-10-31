#!/usr/bin/env bash
# modules/setup-xray.sh — install xray manually if missing
set -euo pipefail

# Import utils (kalau ada)
if [ -f "$(dirname "$0")/../utils.sh" ]; then
  source "$(dirname "$0")/../utils.sh"
else
  echo_log(){ echo "[*] $*"; }
  err_log(){ echo "[!] $*" >&2; }
  run_sudo(){ if [ "$(id -u)" -eq 0 ]; then bash -c "$*"; else sudo bash -c "$*"; fi; }
fi

install_xray_manual(){
  local ver="1.9.11"
  local arch="amd64"
  local tmp
  tmp="$(mktemp -d)"
  cd "$tmp" || return 1

  echo_log "[*] Downloading Xray v$ver ($arch)..."
  local url="https://github.com/chaitin/xray/releases/download/v${ver}/xray_linux_${arch}.zip"
  if ! curl -fsSL -o xray.zip "$url"; then
    err_log "❌ Failed to download $url"
    rm -rf "$tmp"
    return 1
  fi

  echo_log "[*] Extracting Xray..."
  unzip -oq xray.zip || { err_log "❌ Failed to unzip"; rm -rf "$tmp"; return 1; }

  local binfile
  binfile="$(find . -maxdepth 1 -type f -name 'xray*' | head -n1 || true)"
  if [ -z "$binfile" ]; then
    err_log "❌ Binary not found after extraction!"
    rm -rf "$tmp"
    return 1
  fi

  chmod +x "$binfile"
  mv "$binfile" xray

  echo_log "[*] Creating directory /opt/xray..."
  run_sudo "mkdir -p /opt/xray"
  run_sudo "mv -f xray /opt/xray/xray"
  run_sudo "chmod +x /opt/xray/xray"

  echo_log "[*] Generating default configs..."
  run_sudo "cd /opt/xray && ./xray >/dev/null 2>&1 || true"

  # Create global wrapper
  run_sudo "tee /usr/local/bin/xray >/dev/null" <<'EOF'
#!/usr/bin/env bash
cd /opt/xray
exec ./xray "$@"
EOF
  run_sudo "chmod +x /usr/local/bin/xray"

  echo_log "[+] ✅ Xray v$ver installed successfully — run 'xray version' to test"
  cd - >/dev/null 2>&1 || true
  rm -rf "$tmp"
}

# === Run installer ===
if command -v xray >/dev/null 2>&1; then
  echo_log "[=] Xray already installed — skipping."
else
  install_xray_manual
fi
