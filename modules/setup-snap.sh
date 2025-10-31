#!/usr/bin/env bash
# modules/setup-snap.sh
set -euo pipefail
source "$(dirname "$0")/../utils.sh" || true

# === SNAP INSTALLS ===
install_snap_apps(){
  if ! command -v snap >/dev/null 2>&1; then
    echo_log "Installing snapd..."
    run_sudo "apt-get update -y && apt-get install -y snapd" >>"$LOGFILE" 2>&1 || err_log "snapd install failed"
    run_sudo "systemctl enable --now snapd.socket" >>"$LOGFILE" 2>&1 || true
  fi

  if ! command -v feroxbuster >/dev/null 2>&1; then
    echo_log "Installing feroxbuster via snap..."
    run_sudo "snap install feroxbuster" >>"$LOGFILE" 2>&1 || err_log "snap install feroxbuster failed"
    [ -x /snap/bin/feroxbuster ] && run_sudo "ln -sf /snap/bin/feroxbuster /usr/local/bin/feroxbuster" || true
  else
    echo_log "feroxbuster present"
  fi

  if ! command -v amass >/dev/null 2>&1; then
    echo_log "Installing amass via snap..."
    run_sudo "snap install amass" >>"$LOGFILE" 2>&1 || err_log "snap install amass failed"
  else
    echo_log "amass present"
  fi
}

# === NAABU ===
install_naabu(){
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
}

# === TRUFFLEHOG ===
install_trufflehog(){
  echo "[*] Installing Trufflehog (TruffleSecurity)..."
  if ! command -v trufflehog >/dev/null 2>&1; then
    tmpdir=$(mktemp -d)
    git clone --depth 1 https://github.com/trufflesecurity/trufflehog.git "$tmpdir/trufflehog"
    cd "$tmpdir/trufflehog"
    echo "[*] Building trufflehog binary..."
    go build -o trufflehog . || { echo "[!] Go build failed, trying go install fallback..."; go install . || { echo "[❌] Trufflehog build failed!"; exit 1; }; }
    sudo mv trufflehog /usr/local/bin/
    sudo chmod +x /usr/local/bin/trufflehog
    cd - >/dev/null
    rm -rf "$tmpdir"
    echo "[+] Trufflehog installed successfully ✅"
  else
    echo "[=] Trufflehog already installed — skipping."
  fi
}

# === CHAOS-CLIENT ===
install_chaos(){
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
}

# === RUN ALL ===
install_naabu
install_trufflehog
install_chaos
install_snap_apps
