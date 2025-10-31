#!/usr/bin/env bash
# modules/setup-go.sh
# Fokus: Install semua tools berbasis Go (tanpa Chromium/Chrome)
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../utils.sh"

declare -A GO_MAP=(
  ["github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"]="subfinder"
  ["github.com/tomnomnom/assetfinder@latest"]="assetfinder"
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
  ["github.com/tomnomnom/httprobe@latest"]="httprobe"
)

# ✅ fungsi pastikan Go terinstal
ensure_go() {
  if command -v go >/dev/null 2>&1; then
    echo_log "Go found: $(go version)"
  else
    echo_log "Installing Go..."
    run_sudo "apt-get update -y && apt-get install -y golang-go" >>"$LOGFILE" 2>&1 \
      || err_log "install go failed"
  fi
}  # <<<< TUTUPNYA DI SINI, tadinya hilang

# --- improved: parallel go installs with logs + relocate ---
install_go_tools_all() {
  ensure_go
  gpath="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
  mkdir -p "$gpath/bin"
  echo_log "GOPATH: $gpath; installing go packages (parallel)..."

  WORKERS="$(nproc 2>/dev/null || echo 4)"
  echo_log "Using $WORKERS parallel workers for 'go install'"

  tmp_list="$(mktemp)"
  printf "%s\n" "${!GO_MAP[@]}" > "$tmp_list"

  if ! command -v xargs >/dev/null 2>&1 || ! command -v timeout >/dev/null 2>&1; then
    err_log "xargs or timeout missing — please install coreutils or util-linux"
    FAILED+=("go-parallel-prereq")
    rm -f "$tmp_list"
    return 1
  fi

  results="$LOGDIR/go_parallel_results_$(date +%s).txt"
  printf "%s\n" "" > "$results"

  xargs -a "$tmp_list" -n1 -P"$WORKERS" -I{} bash -c '
    pkg="{}"
    name="$(basename "${pkg%@*}")"
    logf="'"$LOGDIR"'/go_install_${name//\//_}.log"
    echo "[`date +%H:%M:%S`] Installing $pkg ..." >>"$logf"
    if timeout 900s bash -c "GO111MODULE=on go install $pkg" >>"$logf" 2>&1; then
      echo "$name:OK"
    else
      echo "$name:FAIL"
    fi
  ' > "$results.tmp" 2>&1 || true

  mv -f "$results.tmp" "$results" 2>/dev/null || true
  rm -f "$tmp_list"

  while read -r line || [ -n "$line" ]; do
    name="${line%%:*}"
    status="${line#*:}"
    if [ "$status" = "OK" ]; then
      if [ -x "$gpath/bin/$name" ]; then
        run_sudo "mv -f '$gpath/bin/$name' /usr/local/bin/" >/dev/null 2>&1 || mv -f "$gpath/bin/$name" /usr/local/bin/ || true
        run_sudo "chmod +x '/usr/local/bin/$name'" >/dev/null 2>&1 || chmod +x "/usr/local/bin/$name" || true
        echo_log "[+] Installed $name -> /usr/local/bin/$name"
      else
        relocate_binary "$name" || true
      fi
      SUCCESS+=("$name")
    else
      err_log "FAILED: $name"
      FAILED+=("$name")
    fi
  done < "$results"

  echo_log "Parallel go install done. Successes: ${#SUCCESS[@]}, Failed: ${#FAILED[@]}"
  return 0
}

# 🔹 Aquatone manual installer (no Chrome)
install_aquatone_no_browser() {
  local bin=aquatone
  if command -v "$bin" >/dev/null 2>&1; then
    echo_log "[=] aquatone already installed"
    return
  fi

  echo_log "[*] Installing aquatone (headless mode, no Chromium)..."
  tmp="$(mktemp -d)"
  local ver="1.7.0"
  local zipurl="https://github.com/michenriksen/aquatone/releases/download/v${ver}/aquatone_linux_amd64_${ver}.zip"
  curl -sL -o "$tmp/aquatone.zip" "$zipurl" >>"$LOGFILE" 2>&1 \
    || { err_log "aquatone download failed"; rm -rf "$tmp"; return; }
  unzip -o "$tmp/aquatone.zip" -d "$tmp" >>"$LOGFILE" 2>&1 \
    || { err_log "aquatone unzip failed"; rm -rf "$tmp"; return; }

  if [ -f "$tmp/aquatone" ]; then
    chmod +x "$tmp/aquatone"
    run_sudo "mv -f '$tmp/aquatone' /usr/local/bin/$bin" || mv -f "$tmp/aquatone" /usr/local/bin/$bin
    echo_log "[+] aquatone installed successfully (no Chromium)"
  else
    err_log "❌ aquatone binary missing after unzip"
  fi
  rm -rf "$tmp"
}

# 🔸 Jalankan semua bagian
install_go_tools_all
install_aquatone_no_browser
