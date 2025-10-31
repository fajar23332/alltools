#!/usr/bin/env bash
# modules/setup-apt.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

install_xray_manual(){
  ver="1.9.11"
  arch="amd64"
  tmp="$(mktemp -d)"
  cd "$tmp" || return 1

  echo_log "[*] Downloading xray v$ver ($arch)..."
  url="https://github.com/chaitin/xray/releases/download/v${ver}/xray_linux_${arch}.zip"

  if ! curl -fsSL -o xray.zip "$url"; then
    err_log "❌ Failed to download $url"
    return 1
  fi

  echo_log "[*] Extracting..."
  if ! unzip -oq xray.zip; then
    err_log "❌ Failed to unzip xray.zip"
    return 1
  fi

  # cari nama file yang cocok (kadang bisa beda)
  binfile="$(find . -maxdepth 1 -type f -name 'xray*' | head -n1 || true)"
  if [ -z "$binfile" ]; then
    err_log "❌ Binary not found after extraction!"
    cd - >/dev/null 2>&1 || true
    rm -rf "$tmp"
    return 1
  fi

  chmod +x "$binfile"
  mv "$binfile" xray

  # run dua kali buat generate default config
  echo_log "[*] Priming default configs..."
  ./xray >/dev/null 2>&1 || true
  ./xray >/dev/null 2>&1 || true

  run_sudo "mkdir -p /opt/xray"
  run_sudo "mv -f xray /opt/xray/xray"
  if [ -d configs ]; then
    run_sudo "cp -r configs /opt/xray/"
  fi
  run_sudo "chmod +x /opt/xray/xray"

  # bikin wrapper biar xray bisa dijalankan dari mana aja
  run_sudo "tee /usr/local/bin/xray >/dev/null" <<'EOF'
#!/usr/bin/env bash
cd /opt/xray
exec ./xray "$@"
EOF
  run_sudo "chmod +x /usr/local/bin/xray"

  echo_log "[+] ✅ Xray v$ver installed successfully in /opt/xray"
  cd - >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
