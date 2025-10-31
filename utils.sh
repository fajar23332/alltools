#!/usr/bin/env bash
# modules/utils.sh — shared helper functions for all modules
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

# === Logging Setup ===
LOGDIR="${LOGDIR:-$(pwd)/install_logs}"
mkdir -p "$LOGDIR"
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log}"

echo_log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
err_log(){ echo "[$(date +%H:%M:%S)] ERROR: $*" | tee -a "$LOGFILE" >&2; }

# === Root Helpers ===
is_root(){ [[ "$(id -u)" == "0" ]]; }
run_sudo(){
  if is_root; then bash -c "$*"; else sudo bash -c "$*"; fi
}

# === Optimized binary check (fast, no deep loop) ===
is_installed_bin(){
  local bin="$1"
  # check normal PATH first (super fast)
  if command -v "$bin" >/dev/null 2>&1; then return 0; fi
  # fallback dirs
  local gopath
  gopath="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
  local paths=("/usr/local/bin" "/usr/bin" "$HOME/.local/bin" "$gopath/bin" "/snap/bin")
  for p in "${paths[@]}"; do
    [ -x "$p/$bin" ] && return 0
  done
  return 1
}

# === Fast get_version (non-blocking + timeout) ===
get_version(){
  local bin="$1"
  local exe out flag
  local TO=2  # seconds timeout, tweak as needed

  exe="$(command -v "$bin" 2>/dev/null || echo "$bin")"

  # try minimal flags (reduce hang risk)
  for flag in "--version" "-v" "-V" "version"; do
    out="$(timeout ${TO}s "$exe" "$flag" 2>/dev/null | head -n1 || true)"
    if [[ -n "$out" ]]; then
      echo "$out" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
      return 0
    fi
  done

  # last resort: plain call (some print version by default)
  out="$(timeout ${TO}s "$exe" 2>/dev/null | head -n1 || true)"
  if [[ -n "$out" ]]; then
    echo "$out" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
    return 0
  fi

  echo "unknown"
  return 1
}

# === Semver Compare Helper ===
# Returns 0 if version A >= version B
ver_ge(){
  printf '%s\n%s\n' "$1" "$2" | awk -F. '{
    for(i=1;i<=3;i++){ a[i]=$i+0 }
    getline; for(i=1;i<=3;i++){ b[i]=$i+0 }
    for(i=1;i<=3;i++){
      if(a[i]>b[i]){ print "1"; exit }
      else if(a[i]<b[i]){ print "0"; exit }
    }
    print "1"
  }' | grep -q 1
}

# === Optional: Quick summary helper ===
quick_summary(){
  local total="$1" found="$2"
  local pct=$(( found * 100 / total ))
  echo_log "Summary: ${found}/${total} tools found (${pct}%)"
}
