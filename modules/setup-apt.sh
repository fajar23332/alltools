#!/usr/bin/env bash
# modules/setup-apt.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

apt_pkgs=( sqlmap masscan nmap whatweb ruby-full )

install_or_upgrade_apt(){
  run_sudo "apt-get update -y" >>"$LOGFILE" 2>&1
  for pkg in "${apt_pkgs[@]}"; do
    if dpkg -s "$pkg" >/dev/null 2>&1; then
      echo_log "APT: $pkg already installed — attempting upgrade"
      run_sudo "apt-get install --only-upgrade -y $pkg" >>"$LOGFILE" 2>&1 || err_log "Upgrade $pkg failed"
    else
      echo_log "APT: Installing $pkg"
      run_sudo "apt-get install -y $pkg" >>"$LOGFILE" 2>&1 || err_log "Install $pkg failed"
    fi
  done

#gobuster
if ! command -v gobuster >/dev/null 2>&1; then
  echo_log "[*] Installing gobuster from apt..."
  run_sudo "apt-get install -y gobuster" >>"$LOGFILE" 2>&1 || err_log "Gobuster install failed"
else
  echo_log "[=] gobuster present"
fi

  # wpscan via gem (idempotent)
  if ! command -v wpscan >/dev/null 2>&1; then
    run_sudo "gem install wpscan" >>"$LOGFILE" 2>&1 || err_log "gem install wpscan failed"
  else
 echo_log "wpscan present"
  fi
}
