#!/usr/bin/env bash
# modules/setup-go.sh
# Fokus: Install semua tools berbasis Go (tanpa Chromium/Chrome)
set -euo pipefail
source "$(dirname "$0")/utils.sh"

declare -A GO_MAP=(
  ["github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"]="subfinder"
  ["github.com/tomnomnom/assetfinder@latest"]="assetfinder"
  ["github.com/projectdiscovery/naabu/v2/cmd/naabu@latest"]="naabu"
  ["github.com/projectdiscovery/dnsx/cmd/dnsx@latest"]="dnsx"
  ["github.com/projectdiscovery/httpx/cmd/httpx@latest"]="httpx"
  ["github.com/ffuf/ffuf@latest"]="ffuf"
  ["github.com/lc/gau/v2/cmd/gau@latest"]="gau"
  ["github.com/tomnomnom/waybackurls@latest"]="waybackurls"
  ["github.com/jaeles-project/gospider@latest"]="gospider"
  ["github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"]="nuclei"
  ["github.com/haccer/subjack@latest"]="subjack"
  ["github.com/hahwul/dalfox/v2@latest"]="dalfox"
  ["github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest"]="shuffledns"
  ["github.com/bp0lr/gauplus@latest"]="gauplus"
  ["github.com/sensepost/gowitness@latest"]="gowitness"
  ["github.com/trufflesecurity/trufflehog@latest"]="trufflehog"
  ["github.com/tomnomnom/httprobe@latest"]="httprobe"
  ["github.com/projectdiscovery/chaos-client@latest"]="chaos-client"
)

ensure_go(){
  if command -v go >/dev/null 2>&1; then
    echo_log "Go found: $(go version)"
  else
    echo_log "Installing Go..."
    run_sudo "apt-get update -y && apt-get install -y golang-go" >>"$LOGFILE" 2>&1 || err_log "install go failed"
  fi
}

install_go_tools(){
  ensure_go
  for pkg in "${!GO_MAP[@]}"; do
    bin="${GO_MAP[$pkg]}"
    if is_installed_bin "$bin"; then
      echo_log "Updating Go tool: $bin"
    else
      echo_log "Installing Go tool: $bin"
    fi

    if timeout 600s bash -c "GO111MODULE=on go install $pkg" >>"$LOGFILE" 2>&1; then
      gopath="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
      if [ -x "$gopath/bin/$bin" ]; then
        run_sudo "mv -f '$gopath/bin/$bin' /usr/local/bin/" || mv -f "$gopath/bin/$bin" /usr/local/bin/
        run_sudo "chmod +x /usr/local/bin/$bin" || chmod +x /usr/local/bin/$bin
      fi
      echo_log "[+] Installed/Updated $bin successfully"
    else
      err_log "❌ Failed installing $bin"
    fi
  done
}

# 🔹 Aquatone manual installer (no Chrome)
install_aquatone_no_browser(){
  local bin=aquatone
  if command -v "$bin" >/dev/null 2>&1; then
    echo_log "[=] aquatone already installed"
    return
  fi

  echo_log "[*] Installing aquatone (headless mode, no Chromium)..."
  tmp="$(mktemp -d)"
  local ver="1.7.0"
  local zipurl="https://github.com/michenriksen/aquatone/releases/download/v${ver}/aquatone_linux_amd64_${ver}.zip"
  curl -sL -o "$tmp/aquatone.zip" "$zipurl" >>"$LOGFILE" 2>&1 || { err_log "aquatone download failed"; rm -rf "$tmp"; return; }
  unzip -o "$tmp/aquatone.zip" -d "$tmp" >>"$LOGFILE" 2>&1 || { err_log "aquatone unzip failed"; rm -rf "$tmp"; return; }

  if [ -f "$tmp/aquatone" ]; then
    chmod +x "$tmp/aquatone"
    run_sudo "mv -f '$tmp/aquatone' /usr/local/bin/$bin" || mv -f "$tmp/aquatone" /usr/local/bin/$bin
    echo_log "[+] aquatone installed successfully (no Chromium)"
  else
    err_log "❌ aquatone binary missing after unzip"
  fi
  rm -rf "$tmp"
}

# Jalankan semua bagian
install_go_tools
install_aquatone_no_browser
