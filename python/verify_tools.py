#!/usr/bin/env bash
# modules/setup-python.sh
# pipx + Sublist3r installer (robust untuk sudo/non-sudo)
set -euo pipefail

# lokasi project root (asumsi modules di repo)
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ambil real user & home (support ketika script dijalankan via sudo)
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo "~${REAL_USER}")"
[ -d "$REAL_HOME" ] || REAL_HOME="$HOME"

# logging helpers (fallback simple jika utils tidak di-source)
LOGDIR="${LOGDIR:-$SCRIPT_ROOT/install_logs}"
mkdir -p "$LOGDIR"
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log"}"
echo_log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
err_log(){ echo "[$(date +%H:%M:%S)] ERROR: $*" | tee -a "$LOGFILE" >&2; }

# run_sudo helper
is_root(){ [[ "$(id -u)" == "0" ]]; }
run_sudo(){
  if is_root; then bash -c "$*"; else sudo bash -c "$*"; fi
}

# ensure pipx available for this session (and add to PATH if user-local)
ensure_pipx(){
  if command -v pipx >/dev/null 2>&1; then
    echo_log "pipx found"
    return 0
  fi

  echo_log "Installing pipx (user) ..."
  # ensure pip/python present
  if ! command -v python3 >/dev/null 2>&1; then
    echo_log "python3 not found - installing python3"
    run_sudo "apt-get update -y && apt-get install -y python3 python3-venv python3-pip" >>"$LOGFILE" 2>&1 || true
  fi

  # install pipx into user (real user)
  # if running as root for the install, install pipx into REAL_USER via sudo -u
  if [ "$REAL_USER" != "$(id -un)" ]; then
    echo_log "Installing pipx for user: $REAL_USER"
    run_sudo "runuser -l $REAL_USER -c 'python3 -m pip install --user pipx && python3 -m pipx ensurepath'" >>"$LOGFILE" 2>&1 || true
  else
    python3 -m pip install --user pipx >>"$LOGFILE" 2>&1 || err_log "pipx install failed"
    python3 -m pipx ensurepath >>"$LOGFILE" 2>&1 || true
  fi

  # add user-base bin to PATH for this session (so pipx is immediately usable)
  USER_BASE_BIN="$(python3 -m site --user-base 2>/dev/null || true)"
  if [ -n "$USER_BASE_BIN" ]; then
    USER_BASE_BIN="$(python3 -m site --user-base)/bin"
  else
    USER_BASE_BIN="$HOME/.local/bin"
  fi
  if [ -d "$USER_BASE_BIN" ] && ! echo "$PATH" | grep -q "$USER_BASE_BIN"; then
    export PATH="$USER_BASE_BIN:$PATH"
    echo_log "Added $USER_BASE_BIN to PATH for this session"
  fi

  if command -v pipx >/dev/null 2>&1; then
    echo_log "pipx ready"
  else
    err_log "pipx not available after install - you may need to log out/in"
  fi
}

# python CLIs to manage via pipx
PIPX_TOOLS=( httpx pwncat )

install_or_update_pipx(){
  ensure_pipx
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

# Sublist3r special: install into real user's home with venv and create shim
install_sublist3r(){
  # prefer canonical symlink name "sublister"
  if command -v sublister >/dev/null 2>&1 || [ -d "$REAL_HOME/Sublist3r" ]; then
    echo_log "Sublist3r looks present - skipping"
    return
  fi

  tmp="$(mktemp -d)"
  echo_log "Cloning Sublist3r -> $tmp ..."
  git clone --depth 1 https://github.com/aboul3la/Sublist3r.git "$tmp" >>"$LOGFILE" 2>&1 || { err_log "git clone sublist3r failed"; rm -rf "$tmp"; return; }

  echo_log "Creating venv and installing requirements..."
  python3 -m venv "$tmp/.venv" >>"$LOGFILE" 2>&1
  (
    set -e
    source "$tmp/.venv/bin/activate"
    pip install --upgrade pip setuptools wheel >>"$LOGFILE" 2>&1 || true
    pip install -r "$tmp/requirements.txt" >>"$LOGFILE" 2>&1 || pip install --break-system-packages -r "$tmp/requirements.txt" >>"$LOGFILE" 2>&1 || err_log "pip install reqs sublist3r failed"
  )

  # move into real user's home (preserve ownership)
  dest="$REAL_HOME/Sublist3r"
  run_sudo "mv -f '$tmp' '$dest'" || mv -f "$tmp" "$dest"
  # fix ownership if we moved as root
  if [ "$(id -un)" = "root" ] && [ "$REAL_USER" != "root" ]; then
    run_sudo "chown -R $REAL_USER:$REAL_USER '$dest'" || true
  fi

  # create shim in /usr/local/bin (needs sudo) and fallback to ~/.local/bin
  shim="/usr/local/bin/sublister"
  if run_sudo true 2>/dev/null; then
    run_sudo "ln -sf '$dest/sublist3r.py' '$shim'" || true
    run_sudo "chmod +x '$shim'" || true
    echo_log "Sublist3r installed (venv inside $dest/.venv), shim: $shim"
  else
    mkdir -p "$REAL_HOME/.local/bin"
    ln -sf "$dest/sublist3r.py" "$REAL_HOME/.local/bin/sublister" || true
    chmod +x "$REAL_HOME/.local/bin/sublister" || true
    echo_log "Sublist3r installed (venv inside $dest/.venv), shim: $REAL_HOME/.local/bin/sublister"
  fi
}

# === Install XSpear (Ruby gem) ===
install_xspear(){
  echo_log "[*] Installing XSpear (gem)..."
  # ensure ruby/gem present
  if ! command -v gem >/dev/null 2>&1; then
    echo_log "ruby/gem not found -> installing ruby"
    run_sudo "apt-get update -y && apt-get install -y ruby-full build-essential" >>"$LOGFILE" 2>&1 || { err_log "install ruby failed"; return 1; }
  fi

  # install main gem + common dependency gems
  run_sudo "gem install XSpear --no-document" >>"$LOGFILE" 2>&1 || { err_log "gem install XSpear failed"; return 1; }
  # optional dependency fixes
  run_sudo "gem install colorize selenium-webdriver terminal-table progress_bar --no-document" >>"$LOGFILE" 2>&1 || true

  # shim to /usr/local/bin if needed (XSpear binary name: xspear)
  if command -v xspear >/dev/null 2>&1; then
    echo_log "[+] XSpear installed -> $(command -v xspear)"
    SUCCESS+=("xspear")
  else
    echo_log "[!] XSpear gem installed but 'xspear' not in PATH. You may need to add $(ruby -e 'print Gem.user_dir')/bin to PATH"
    FAILED+=("xspear")
  fi
}

# === Install EyeWitness ===
install_eyewitness(){
  echo_log "[*] Installing EyeWitness..."
  if is_installed_bin "eyewitness" || [ -d "$HOME/EyeWitness" ]; then
    echo_log "[=] EyeWitness present — skipping"
    return 0
  fi

  tmp="$(mktemp -d)"
  git clone --depth 1 https://github.com/FortyNorthSecurity/EyeWitness.git "$tmp/EyeWitness" >>"$LOGFILE" 2>&1 || { err_log "git clone eyewitness failed"; rm -rf "$tmp"; return 1; }
  # run setup script inside repo
  cd "$tmp/EyeWitness/setup" || { err_log "cd eyewitness setup failed"; rm -rf "$tmp"; return 1; }
  run_sudo "./setup.sh" >>"$LOGFILE" 2>&1 || { err_log "eyewitness setup.sh failed (try manual)"; }
  cd "$tmp" || true

  # move to HOME and create shim
  run_sudo "mv -f '$tmp/EyeWitness' '$HOME/EyeWitness'" || mv -f "$tmp/EyeWitness" "$HOME/EyeWitness"
  ln -sf "$HOME/EyeWitness/EyeWitness.py" /usr/local/bin/eyewitness || true
  chmod +x "$HOME/EyeWitness/EyeWitness.py" || true

  # If venv name is eyewitness-venv, note how to activate in README
  echo_log "[+] EyeWitness installed (venv inside $HOME/EyeWitness). Use: source $HOME/EyeWitness/eyewitness-venv/bin/activate && python EyeWitness.py"
  SUCCESS+=("eyewitness")
  rm -rf "$tmp"
}

# === Install goth (build example app) ===
install_goth_example(){
  echo_log "[*] Installing Goth example (optional) ..."
  if [ -d "$HOME/goth" ]; then
    echo_log "[=] goth repo already cloned - skipping"
    return 0
  fi

  # ensure go present
  if ! command -v go >/dev/null 2>&1; then
    echo_log "Go not found - installing via apt"
    run_sudo "apt-get update -y && apt-get install -y golang-go" >>"$LOGFILE" 2>&1 || { err_log "install go failed"; return 1; }
  fi

  git clone --depth 1 https://github.com/markbates/goth.git "$HOME/goth" >>"$LOGFILE" 2>&1 || { err_log "git clone goth failed"; return 1; }
  # build the example
  cd "$HOME/goth/examples" || return 0
  # fetch example deps
  go get ./... >>"$LOGFILE" 2>&1 || true
  go build -v ./... >>"$LOGFILE" 2>&1 || true

  echo_log "[+] goth examples cloned at $HOME/goth/examples — read README to run examples (requires provider keys)"
  SUCCESS+=("goth-example")
}

# === Run steps ===
install_or_update_pipx
install_sublist3r

# Tambahan tools baru
install_xspear          # Ruby-based XSS scanner (ganti xssfinder)
install_eyewitness      # Screenshot & recon visualizer (Python)
install_goth_example    # Optional: OAuth example builder

echo_log "modules/setup-python.sh finished."
