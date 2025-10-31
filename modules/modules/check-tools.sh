#!/usr/bin/env bash
# modules/setup-apt.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

TOOLS=(
  subfinder assetfinder amass gau waybackurls httpx naabu dnsx nuclei ffuf
  feroxbuster gobuster gospider httprobe chaos-client sqlmap masscan nmap
  whatweb wpscan eyewitness trufflehog subjack sublister shuffledns sensitivefinder
  goth aquatone dalfox whatweb2 xssfinder gowitness gauplus subfinder2
)

echo_log "Running tool inventory check..."
found=0; missing=()
for t in "${TOOLS[@]}"; do
  if is_installed_bin "$t"; then
    v="$(get_version "$t" 2>/dev/null || echo unknown)"
    echo -e "  \e[32m✔\e[0m $t — $v"
    found=$((found+1))
  else
    echo -e "  \e[31m✖\e[0m $t"
    missing+=("$t")
  fi
done

echo_log "Summary: $found/${#TOOLS[@]} tools found"
if [ ${#missing[@]} -gt 0 ]; then
  echo_log "Missing: ${missing[*]}"
fi
