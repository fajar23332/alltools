#!/usr/bin/env bash
# modules/setup-snap.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

install_snap_apps(){
  if ! command -v snap >/dev/null 2>&1; then
    echo_log "Installing snapd..."
    run_sudo "apt-get update -y && apt-get install -y snapd" >>"$LOGFILE" 2>&1 || err_log "snapd install failed"
    run_sudo "systemctl enable --now snapd.socket" >>"$LOGFILE" 2>&1 || true
  fi

  # feroxbuster
  if ! command -v feroxbuster >/dev/null 2>&1; then
    echo_log "Installing feroxbuster via snap..."
    run_sudo "snap install feroxbuster" >>"$LOGFILE" 2>&1 || err_log "snap install feroxbuster failed"
    [ -x /snap/bin/feroxbuster ] && run_sudo "ln -sf /snap/bin/feroxbuster /usr/local/bin/feroxbuster" || true
  else
    echo_log "feroxbuster present"
  fi

  # amass (snap fallback)
  if ! command -v amass >/dev/null 2>&1; then
    echo_log "Installing amass via snap..."
    run_sudo "snap install amass" >>"$LOGFILE" 2>&1 || err_log "snap install amass failed"
  else
    echo_log "amass present"
  fi
}

install_snap_apps
