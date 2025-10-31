#!/usr/bin/env bash
# modules/setup-python.sh
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo "~${REAL_USER}")"
[ -d "$REAL_HOME" ] || REAL_HOME="$HOME"

LOGDIR="${LOGDIR:-$SCRIPT_ROOT/install_logs}"
mkdir -p "$LOGDIR"
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log}"

echo_log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
err_log(){ echo "[$(date +%H:%M:%S)] ERROR: $*" | tee -a "$LOGFILE" >&2; }
SUCCESS=(); FAILED=()

is_root(){ [[ "$(id -u)" == "0" ]]; }
run_sudo(){ if is_root; then bash -c "$*"; else sudo bash -c "$*"; fi; }

# 🔧 helper untuk cek binary (dipakai di EyeWitness)
is_installed_bin(){
  command -v "$1" >/dev/null 2>&1 && return 0
  [ -x "/usr/local/bin/$1" ] && return 0
  [ -x "$REAL_HOME/.local/bin/$1" ] && return 0
  return 1
}

# === pipx handler ===
ensure_pipx(){
  if command -v pipx >/dev/null 2>&1; then
    echo_log "pipx found"
    return 0
  fi

  echo_log "Installing pipx ..."
  if ! command -v python3 >/dev/null 2>&1; then
    run_sudo "apt-get update -y && apt-get install -y python3 python3-venv python3-pip" >>"$LOGFILE" 2>&1 || true
  fi

  if [ "$REAL_USER" != "$(id -un)" ]; then
    run_sudo "runuser -l $REAL_USER -c 'python3 -m pip install --user pipx && python3 -m pipx ensurepath'" >>"$LOGFILE" 2>&1 || true
  else
    python3 -m pip install --user pipx >>"$LOGFILE" 2>&1 || err_log "pipx install failed"
    python3 -m pipx ensurepath >>"$LOGFILE" 2>&1 || true
  fi

  local user_bin
  user_bin="$(python3 -m site --user-base 2>/dev/null)/bin"
  [ -z "$user_bin" ] && user_bin="$REAL_HOME/.local/bin"
  if [ -d "$user_bin" ] && ! grep -q "$user_bin" <<<"$PATH"; then
    export PATH="$user_bin:$PATH"
    echo_log "Added $user_bin to PATH"
  fi
}

PIPX_TOOLS=( httpx pwncat )

install_or_update_pipx(){
  ensure_pipx
  for t in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "^  $t "; then
      echo_log "pipx: upgrading $t"
      pipx upgrade "$t" >>"$LOGFILE" 2>&1 || pipx install "$t" >>"$LOGFILE" 2>&1
    else
      echo_log "pipx: installing $t"
      pipx install "$t" >>"$LOGFILE" 2>&1
    fi
  done
}

# === Sublist3r ===
install_sublist3r(){
  if command -v sublister >/dev/null 2>&1 || [ -d "$REAL_HOME/Sublist3r" ]; then
    echo_log "Sublist3r present — skipping"
    return
  fi

  tmp="$(mktemp -d)"
  echo_log "Cloning Sublist3r ..."
  git clone --depth 1 https://github.com/aboul3la/Sublist3r.git "$tmp" >>"$LOGFILE" 2>&1 || { err_log "clone fail"; return; }

  echo_log "Creating venv..."
  python3 -m venv "$tmp/.venv" >>"$LOGFILE" 2>&1
  (
    set -e
    source "$tmp/.venv/bin/activate"
    pip install -r "$tmp/requirements.txt" >>"$LOGFILE" 2>&1 || true
  )

  dest="$REAL_HOME/Sublist3r"
  run_sudo "mv -f '$tmp' '$dest'" || mv -f "$tmp" "$dest"
  run_sudo "chown -R $REAL_USER:$REAL_USER '$dest'" 2>/dev/null || true

  if run_sudo true 2>/dev/null; then
    run_sudo "ln -sf '$dest/sublist3r.py' /usr/local/bin/sublister" || true
  else
    mkdir -p "$REAL_HOME/.local/bin"
    ln -sf "$dest/sublist3r.py" "$REAL_HOME/.local/bin/sublister"
  fi

  echo_log "Sublist3r installed → $dest"
  SUCCESS+=("sublist3r")
}

# === XSpear ===
install_xspear(){
  echo_log "[*] Installing XSpear (gem)..."
  if ! command -v gem >/dev/null 2>&1; then
    run_sudo "apt-get update -y && apt-get install -y ruby-full build-essential" >>"$LOGFILE" 2>&1 || return 1
  fi

  run_sudo "gem install XSpear --no-document" >>"$LOGFILE" 2>&1 || { err_log "XSpear install failed"; return 1; }
  run_sudo "gem install colorize selenium-webdriver terminal-table progress_bar --no-document" >>"$LOGFILE" 2>&1 || true

  local GEM_BIN_DIR
  GEM_BIN_DIR="$(ruby -e 'print Gem.user_dir')/bin"
  if [ -d "$GEM_BIN_DIR" ]; then
    if ! grep -q "$GEM_BIN_DIR" <<<"$PATH"; then
      export PATH="$GEM_BIN_DIR:$PATH"
      if [ -w "$REAL_HOME/.bashrc" ] && ! grep -q "$GEM_BIN_DIR" "$REAL_HOME/.bashrc" 2>/dev/null; then
        echo "export PATH=\"$GEM_BIN_DIR:\$PATH\"" >> "$REAL_HOME/.bashrc"
      fi
      echo_log "Added Ruby gem bin path: $GEM_BIN_DIR"
    fi
    if [ -f "$GEM_BIN_DIR/xspear" ]; then
      run_sudo "ln -sf '$GEM_BIN_DIR/xspear' /usr/local/bin/xspear"
      run_sudo "chmod +x /usr/local/bin/xspear"
    fi
  fi

  if command -v xspear >/dev/null 2>&1; then
    echo_log "[+] XSpear installed at $(command -v xspear)"
    SUCCESS+=("xspear")
  else
    err_log "[!] XSpear gem installed but not found in PATH"
    FAILED+=("xspear")
  fi
}

# === EyeWitness ===
install_eyewitness(){
  echo_log "[*] Installing EyeWitness..."
  if is_installed_bin "eyewitness" || [ -d "$REAL_HOME/EyeWitness" ]; then
    echo_log "[=] EyeWitness present — skipping"
    return 0
  fi

  tmp="$(mktemp -d)"
  git clone --depth 1 https://github.com/FortyNorthSecurity/EyeWitness.git "$tmp/EyeWitness" >>"$LOGFILE" 2>&1 || return 1
  if [ -d "$tmp/EyeWitness/setup" ]; then
    ( cd "$tmp/EyeWitness/setup" && run_sudo "./setup.sh" >>"$LOGFILE" 2>&1 ) || true
  fi
  run_sudo "mv -f '$tmp/EyeWitness' '$REAL_HOME/EyeWitness'" || mv -f "$tmp/EyeWitness" "$REAL_HOME/EyeWitness"
  run_sudo "chown -R $REAL_USER:$REAL_USER '$REAL_HOME/EyeWitness'" 2>/dev/null || true
  rm -rf "$tmp"

  local EYE_MAIN
  if [ -f "$REAL_HOME/EyeWitness/Python/EyeWitness.py" ]; then
    EYE_MAIN="$REAL_HOME/EyeWitness/Python/EyeWitness.py"
  else
    EYE_MAIN="$REAL_HOME/EyeWitness/EyeWitness.py"
  fi

  if [ -f "$EYE_MAIN" ]; then
    run_sudo "ln -sf '$EYE_MAIN' /usr/local/bin/eyewitness" || ln -sf "$EYE_MAIN" "$REAL_HOME/.local/bin/eyewitness"
    chmod +x "$EYE_MAIN"
    echo_log "[+] EyeWitness linked at $EYE_MAIN"
    SUCCESS+=("eyewitness")
  else
    err_log "[!] EyeWitness main script missing"
    FAILED+=("eyewitness")
  fi
}

# === Goth ===
install_goth_example(){
  echo_log "[*] Installing Goth example..."
  if [ -d "$REAL_HOME/goth" ]; then
    echo_log "[=] goth already cloned — skipping"
    return 0
  fi
  if ! command -v go >/dev/null 2>&1; then
    run_sudo "apt-get update -y && apt-get install -y golang-go" >>"$LOGFILE" 2>&1 || return 1
  fi
  git clone --depth 1 https://github.com/markbates/goth.git "$REAL_HOME/goth" >>"$LOGFILE" 2>&1 || return 1
  ( cd "$REAL_HOME/goth/examples" && go get ./... >>"$LOGFILE" 2>&1 && go build -v ./... >>"$LOGFILE" 2>&1 ) || true
  echo_log "[+] Goth examples ready → $REAL_HOME/goth/examples"
  SUCCESS+=("goth-example")
}

# === Run Steps ===
install_or_update_pipx
install_sublist3r
install_xspear
install_eyewitness
install_goth_example

echo_log "modules/setup-python.sh finished."
