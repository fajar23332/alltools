#!/usr/bin/env bash
# modules/setup-xray.sh — robust installer for Xray by Chaitin
set -euo pipefail

# === Import logger & sudo helpers ===
if [ -f "$(dirname "$0")/../utils.sh" ]; then
  source "$(dirname "$0")/../utils.sh"
else
  echo_log(){ echo "[*] $*"; }
  err_log(){ echo "[!] $*" >&2; }
  run_sudo(){ if [ "$(id -u)" -eq 0 ]; then bash -c "$*"; else sudo bash -c "$*"; fi; }
fi

# === Main installer ===
install_xray_manual(){
  local ver="1.9.11"

  # --- Auto detect arch ---
  local arch="$(uname -m)"
  case "$arch" in
    x86_64) arch="amd64" ;;
    aarch64) arch="arm64" ;;
    armv7l) arch="arm" ;;
    i686|i386) arch="386" ;;
    *) err_log "⚠️ Unknown arch: $arch, fallback to amd64"; arch="amd64" ;;
  esac

  local tmp="$(mktemp -d)"
  cd "$tmp" || return 1

  echo_log "[*] Detected architecture: $arch"
  echo_log "[*] Using version: v$ver"

  # --- Detect downloader ---
  local dl_cmd=""
  if command -v curl >/dev/null 2>&1; then
    dl_cmd="curl -fsSL -o"
  elif command -v wget >/dev/null 2>&1; then
    dl_cmd="wget -qO"
  else
    err_log "❌ Neither curl nor wget found. Please install one of them."
    return 1
  fi

  # --- Try both GitHub URL formats ---
  local base="https://github.com/chaitin/xray/releases/download"
  local url1="$base/${ver}/xray_linux_${arch}.zip"
  local url2="$base/v${ver}/xray_linux_${arch}.zip"

  echo_log "[*] Downloading Xray binary..."
  if ! eval "$dl_cmd xray.zip \"$url1\"" 2>/dev/null; then
    echo_log "[!] Primary URL failed, retrying alternate tag..."
    if ! eval "$dl_cmd xray.zip \"$url2\"" 2>/dev/null; then
      err_log "❌ Both URLs failed (checked $url1 and $url2)"
      rm -rf "$tmp"
      return 1
    fi
  fi

  echo_log "[*] Extracting Xray..."
  if ! unzip -oq xray.zip; then
    err_log "❌ Failed to unzip archive"
    rm -rf "$tmp"
    return 1
  fi

  # --- Find binary file ---
  local binfile
  binfile="$(find . -maxdepth 1 -type f -name 'xray*' | head -n1 || true)"
  if [ -z "$binfile" ]; then
    err_log "❌ Xray binary not found after extraction!"
    rm -rf "$tmp"
    return 1
  fi

  # --- Rename first, then chmod ---
  mv "$binfile" xray
  chmod +x xray

  # --- Validate binary format ---
  if ! file xray | grep -q "ELF"; then
    err_log "❌ Downloaded file is not a valid ELF binary (maybe corrupted)"
    rm -rf "$tmp"
    return 1
  fi

  # --- Prepare install directory ---
  echo_log "[*] Installing to /opt/xray..."
  run_sudo "mkdir -p /opt/xray"
  run_sudo "mv -f xray /opt/xray/xray"
  run_sudo "chmod +x /opt/xray/xray"

  # --- Generate default configs once ---
  echo_log "[*] Generating default config files..."
  run_sudo "cd /opt/xray && ./xray >/dev/null 2>&1 || true"

  # --- Create wrapper so xray can be run anywhere ---
  echo_log "[*] Creating global launcher /usr/local/bin/xray"
  run_sudo "tee /usr/local/bin/xray >/dev/null" <<'EOF'
#!/usr/bin/env bash
cd /opt/xray
exec ./xray "$@"
EOF
  run_sudo "chmod +x /usr/local/bin/xray"

  echo_log "[✅] Xray v$ver installed successfully!"
  echo_log "[ℹ️] You can run it from anywhere with: xray version"

  cd - >/dev/null 2>&1 || true
  rm -rf "$tmp"
}

# === Execute if not installed ===
if command -v xray >/dev/null 2>&1; then
  echo_log "[=] Xray already installed — skipping."
else
  install_xray_manual
fi
