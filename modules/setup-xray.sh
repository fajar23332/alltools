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


#!/usr/bin/env bash
set -euo pipefail

echo "=== Installing Naabu, Trufflehog, and Chaos-Client ==="

# Ensure Go
if ! command -v go >/dev/null 2>&1; then
  echo "[*] Installing Go..."
  sudo apt update -y && sudo apt install -y golang
  export PATH=$PATH:/usr/local/go/bin
fi

# === 1️⃣ Install Naabu ===
echo "[*] Installing Naabu (ProjectDiscovery)..."
if ! command -v naabu >/dev/null 2>&1; then
  tmpdir=$(mktemp -d)
  cd "$tmpdir"
  curl -sL "$(curl -s https://api.github.com/repos/projectdiscovery/naabu/releases/latest \
    | grep browser_download_url | grep linux | grep amd64 | cut -d '"' -f 4 | head -n1)" \
    -o naabu.zip
  unzip -o naabu.zip
  sudo mv naabu*/naabu /usr/local/bin/naabu 2>/dev/null || sudo mv naabu /usr/local/bin/naabu
  sudo chmod +x /usr/local/bin/naabu
  cd - >/dev/null
  rm -rf "$tmpdir"
  echo "[+] Naabu installed successfully ✅"
else
  echo "[=] Naabu already installed — skipping."
fi

# === 2️⃣ Install Trufflehog ===
echo "[*] Installing Trufflehog (TruffleSecurity)..."
if ! command -v trufflehog >/dev/null 2>&1; then
  tmpdir=$(mktemp -d)
  git clone --depth 1 https://github.com/trufflesecurity/trufflehog.git "$tmpdir/trufflehog"
  cd "$tmpdir/trufflehog"

  # versi baru: build langsung dari root
  echo "[*] Building trufflehog binary..."
  go build -o trufflehog . || {
    echo "[!] Go build failed, trying go install fallback..."
    go install . || { echo "[❌] Trufflehog build failed!"; exit 1; }
  }

  sudo mv trufflehog /usr/local/bin/
  sudo chmod +x /usr/local/bin/trufflehog
  cd - >/dev/null
  rm -rf "$tmpdir"
  echo "[+] Trufflehog installed successfully ✅"
else
  echo "[=] Trufflehog already installed — skipping."
fi

# === 3️⃣ Install Chaos-Client ===
echo "[*] Installing Chaos-Client (ProjectDiscovery)..."
if ! command -v chaos-client >/dev/null 2>&1; then
  tmpdir=$(mktemp -d)
  cd "$tmpdir"
  curl -sL "$(curl -s https://api.github.com/repos/projectdiscovery/chaos-client/releases/latest \
    | grep browser_download_url | grep linux | grep amd64 | cut -d '"' -f 4 | head -n1)" \
    -o chaos.zip
  unzip -o chaos.zip
  sudo mv chaos*/chaos-client /usr/local/bin/chaos-client 2>/dev/null || sudo mv chaos-client /usr/local/bin/chaos-client
  sudo chmod +x /usr/local/bin/chaos-client
  cd - >/dev/null
  rm -rf "$tmpdir"
  echo "[+] Chaos-Client installed successfully ✅"
else
  echo "[=] Chaos-Client already installed — skipping."
fi

echo "=== All tools installed successfully ==="
naabu -version || echo "naabu ready"
trufflehog --version || echo "trufflehog ready"
chaos-client -version || echo "chaos-client ready"
