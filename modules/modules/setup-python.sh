#!/usr/bin/env bash
# modules/setup-python.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

# ensure pipx
if command -v pipx >/dev/null 2>&1; then
  echo_log "pipx found"
else
  echo_log "Installing pipx..."
  run_sudo "apt-get install -y python3-pip python3-venv" >>"$LOGFILE" 2>&1 || true
  python3 -m pip install --user pipx >>"$LOGFILE" 2>&1 || err_log "pipx install failed"
  python3 -m pipx ensurepath >>"$LOGFILE" 2>&1 || true
fi

# python CLIs to manage via pipx
PIPX_TOOLS=( httpx pwncat )

install_or_update_pipx(){
  for t in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "^  $t "; then
      echo_log "pipx: $t already installed — upgrading"
      pipx upgrade "$t" >>"$LOGFILE" 2>&1 || pipx install "$t" >>"$LOGFILE" 2>&1 || err_log "pipx upgrade/install $t failed"
    else
      echo_log "pipx: Installing $t"
      pipx install "$t" >>"$LOGFILE" 2>&1 || err_log "pipx install $t failed"
    fi
  done
}

# Sublist3r special: install into virtualenv and create shim
install_sublist3r(){
  if is_installed_bin "sublister" || [ -d "$HOME/Sublist3r" ]; then
    echo_log "Sublist3r looks present - skipping"
    return
  fi
  tmp="/tmp/Sublist3r-$(date +%s)"
  rm -rf "$tmp"
  git clone https://github.com/aboul3la/Sublist3r.git "$tmp" >>"$LOGFILE" 2>&1 || { err_log "git clone sublist3r failed"; return; }
  # create venv and install requirements in it
  python3 -m venv "$tmp/.venv" >>"$LOGFILE" 2>&1
  # activate and install
  # note: use bash subshell so activation does not pollute caller
  (
    source "$tmp/.venv/bin/activate"
    pip install --upgrade pip >>"$LOGFILE" 2>&1
    pip install -r "$tmp/requirements.txt" >>"$LOGFILE" 2>&1 || pip install --break-system-packages -r "$tmp/requirements.txt" >>"$LOGFILE" 2>&1 || err_log "pip install reqs sublist3r failed"
  )
  run_sudo "mv -f '$tmp' '$HOME/Sublist3r'" || mv -f "$tmp" "$HOME/Sublist3r"
  ln -sf "$HOME/Sublist3r/sublist3r.py" /usr/local/bin/sublister || true
  echo_log "Sublist3r installed (venv inside $HOME/Sublist3r/.venv)"
}

install_or_update_pipx
install_sublist3r
