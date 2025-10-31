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
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log}"

echo_log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
err_log(){ echo "[$(date +%H:%M:%S)] ERROR: $*" | tee -a "$LOGFILE" >&2; }

# result trackers (module-local)
SUCCESS=()
FAILED=()

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
    USER_BASE_BIN="$REAL_HOME/.local/bin"
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
  if run_sudo true 2>/dev/null; then
    run_sudo "mv -f '$tmp' '$dest'" || mv -f "$tmp" "$dest"
    run_sudo "chown -R $REAL_USER:$REAL_USER '$dest'" 2>/dev/null || true
  else
    mv -f "$tmp" "$dest"
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

  SUCCESS+=("sublist3r")
}

# === Install XSpear (Ruby gem) ===
install_xspear(){
  echo_log "[*] Installing XSpear (gem)..."
  if ! command -v gem >/dev/null 2>&1; then
    echo_log "ruby/gem not found -> installing ruby"
    run_sudo "apt-get update -y && apt-get install -y ruby-full build-essential" >>"$LOGFILE" 2>&1 || { err_log "install ruby failed"; FAILED+=("xspear"); return 1; }
  fi

  run_sudo "gem install XSpear --no-document" >>"$LOGFILE" 2>&1 || { err_log "gem install XSpear failed"; FAILED+=("xspear"); return 1; }
  run_sudo "gem install colorize selenium-webdriver terminal-table progress_bar --no-document" >>"$LOGFILE" 2>&1 || true

  # locate user gem bin dir and ensure PATH
  GEM_BIN_DIR="$(ruby -e 'print Gem.user_dir')/bin" || GEM_BIN_DIR=""
  if [ -n "$GEM_BIN_DIR" ] && [ -d "$GEM_BIN_DIR" ]; then
    if ! echo "$PATH" | grep -q "$GEM_BIN_DIR"; then
      export PATH="$GEM_BIN_DIR:$PATH"
      # persist for real user
      if [ -n "$REAL_HOME" ] && [ -w "$REAL_HOME/.bashrc" ]; then
        echo "export PATH=\"$GEM_BIN_DIR:\$PATH\"" >> "$REAL_HOME/.bashrc"
      fi
      echo_log "Added gem bin to PATH: $GEM_BIN_DIR"
    fi
  fi

  if command -v xspear >/dev/null 2>&1; then
    echo_log "[+] XSpear installed -> $(command -v xspear)"
    SUCCESS+=("xspear")
  else
    echo_log "[!] XSpear gem installed but 'xspear' not in PATH. Check $GEM_BIN_DIR"
    FAILED+=("xspear")
  fi
}
# === Install EyeWitness ===
install_eyewitness(){
  echo_log "[*] Installing EyeWitness..."
  if is_installed_bin "eyewitness" || [ -d "$REAL_HOME/EyeWitness" ]; then
    echo_log "[=] EyeWitness present — skipping"
    return 0
  fi

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  git clone --depth 1 https://github.com/FortyNorthSecurity/EyeWitness.git "$tmp/EyeWitness" >>"$LOGFILE" 2>&1 || { err_log "git clone eyewitness failed"; rm -rf "$tmp"; trap - EXIT; return 1; }

  if [ -d "$tmp/EyeWitness/setup" ]; then
    cd "$tmp/EyeWitness/setup" || { err_log "cd eyewitness setup failed"; rm -rf "$tmp"; trap - EXIT; return 1; }
    run_sudo "./setup.sh" >>"$LOGFILE" 2>&1 || echo_log "eyewitness setup.sh had issues; continue and try manual"
    cd "$tmp" || true
  else
    err_log "eyewitness setup folder missing; continuing with manual placement"
  fi

  # move to real home and symlink to actual script location (Python/)
  if run_sudo true 2>/dev/null; then
    run_sudo "mv -f '$tmp/EyeWitness' '$REAL_HOME/EyeWitness'" || mv -f "$tmp/EyeWitness" "$REAL_HOME/EyeWitness"
    run_sudo "chown -R $REAL_USER:$REAL_USER '$REAL_HOME/EyeWitness'" || true
  else
    mv -f "$tmp/EyeWitness" "$REAL_HOME/EyeWitness"
  fi

  # prefer Python/EyeWitness.py if exists
  if [ -f "$REAL_HOME/EyeWitness/Python/EyeWitness.py" ]; then
    EW_PATH="$REAL_HOME/EyeWitness/Python/EyeWitness.py"
  else
    EW_PATH="$REAL_HOME/EyeWitness/EyeWitness.py"
  fi

  # create shim
  if [ -f "$EW_PATH" ]; then
    if run_sudo true 2>/dev/null; then
      run_sudo "ln -sf '$EW_PATH' /usr/local/bin/eyewitness" || true
      run_sudo "chmod +x '$EW_PATH'" || true
    else
      mkdir -p "$REAL_HOME/.local/bin"
      ln -sf "$EW_PATH" "$REAL_HOME/.local/bin/eyewitness" || true
      chmod +x "$EW_PATH" || true
    fi
    echo_log "[+] EyeWitness installed (venv inside $REAL_HOME/EyeWitness). Use: source $REAL_HOME/EyeWitness/eyewitness-venv/bin/activate && python EyeWitness.py"
    SUCCESS+=("eyewitness")
  else
    err_log "EyeWitness main script not found at expected locations"
    FAILED+=("eyewitness")
  fi

  trap - EXIT
  rm -rf "$tmp"
}

# === Install goth (build example app) ===
install_goth_example(){
  echo_log "[*] Installing Goth example (optional) ..."
  if [ -d "$REAL_HOME/goth" ]; then
    echo_log "[=] goth repo already cloned - skipping"
    return 0
  fi

  # ensure go present
  if ! command -v go >/dev/null 2>&1; then
    echo_log "Go not found - installing via apt"
    run_sudo "apt-get update -y && apt-get install -y golang-go" >>"$LOGFILE" 2>&1 || { err_log "install go failed"; FAILED+=("goth"); return 1; }
  fi

  git clone --depth 1 https://github.com/markbates/goth.git "$REAL_HOME/goth" >>"$LOGFILE" 2>&1 || { err_log "git clone goth failed"; FAILED+=("goth"); return 1; }
  cd "$REAL_HOME/goth/examples" || return 0
  go get ./... >>"$LOGFILE" 2>&1 || true
  go build -v ./... >>"$LOGFILE" 2>&1 || true

  echo_log "[+] goth examples cloned at $REAL_HOME/goth/examples — read README to run examples (requires provider keys)"
  SUCCESS+=("goth-example")
}

# helper: fast check if binary exists (reuse project's util if available)
is_installed_bin(){
  command -v "$1" >/dev/null 2>&1 && return 0
  [ -x "/usr/local/bin/$1" ] && return 0
  [ -x "$REAL_HOME/.local/bin/$1" ] && return 0
  return 1
}

# === Run steps ===
install_or_update_pipx
install_sublist3r

# Tambahan tools baru (eksekusi hanya kalau perlu)
install_xspear          # Ruby-based XSS scanner (ganti xssfinder)
install_eyewitness      # Screenshot & recon visualizer (Python)
install_goth_example    # Optional: OAuth example builder

# === Auto-Fix PATH & Symlink ===

# [Fix XSpear PATH]
if command -v ruby >/dev/null 2>&1; then
  GEM_BIN_PATH="$(ruby -e 'puts Gem.bindir' 2>/dev/null || true)"
  if [ -n "$GEM_BIN_PATH" ] && [ -d "$GEM_BIN_PATH" ]; then
    if ! grep -q "$GEM_BIN_PATH" <<<"$PATH"; then
      echo_log "[+] Adding Ruby gem bin path to PATH: $GEM_BIN_PATH"
      echo "export PATH=\"\$PATH:$GEM_BIN_PATH\"" >> "$REAL_HOME/.bashrc"
      export PATH="$PATH:$GEM_BIN_PATH"
    fi
  fi
fi

# [Fix EyeWitness symlink]
EYE_BASE="$REAL_HOME/EyeWitness"
if [ -d "$EYE_BASE" ]; then
  if [ -f "$EYE_BASE/Python/EyeWitness.py" ]; then
    EYE_MAIN="$EYE_BASE/Python/EyeWitness.py"
  elif [ -f "$EYE_BASE/EyeWitness.py" ]; then
    EYE_MAIN="$EYE_BASE/EyeWitness.py"
  else
    EYE_MAIN=""
  fi

  if [ -n "$EYE_MAIN" ]; then
    echo_log "[+] Linking EyeWitness main script: $EYE_MAIN"
    run_sudo "ln -sf '$EYE_MAIN' /usr/local/bin/eyewitness" || ln -sf "$EYE_MAIN" "$REAL_HOME/.local/bin/eyewitness"
    chmod +x "$EYE_MAIN" || true
  else
    err_log "[!] EyeWitness main script not found, manual check needed."
  fi
fi

echo_log "modules/setup-python.sh finished."
