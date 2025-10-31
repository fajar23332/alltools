#!/usr/bin/env bash
# modules/setup-apt.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

# map go module -> expected binary name
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
  ["github.com/michenriksen/aquatone@latest"]="aquatone"
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
    echo_log "Go not found - installing minimal go via apt"
    run_sudo "apt-get update -y && apt-get install -y golang" >>"$LOGFILE" 2>&1 || err_log "install go failed"
  fi
}

install_or_update_go_tools(){
  ensure_go
  for pkg in "${!GO_MAP[@]}"; do
    bin="${GO_MAP[$pkg]}"
    if is_installed_bin "$bin"; then
      echo_log "Go-tool: $bin exists. Attempting reinstall/update"
    else
      echo_log "Go-tool: $bin not found. Installing"
    fi

    # try install/update (idempotent)
    if timeout 600s bash -c "GO111MODULE=on go install $pkg" >>"$LOGFILE" 2>&1; then
      # try relocate from GOPATH
      gpath="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
      if [ -x "$gpath/bin/$bin" ]; then
        run_sudo "mv -f '$gpath/bin/$bin' /usr/local/bin/" >/dev/null 2>&1 || mv -f "$gpath/bin/$bin" /usr/local/bin/
        run_sudo "chmod +x /usr/local/bin/$bin" || chmod +x /usr/local/bin/$bin
      fi
      echo_log "Go install/update OK: $bin"
    else
      err_log "go install failed for $pkg — check $LOGFILE"
    fi
  done
}
