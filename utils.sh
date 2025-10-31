#!/usr/bin/env bash
# modules/setup-apt.sh
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail


LOGDIR="${LOGDIR:-$(pwd)/install_logs}"
mkdir -p "$LOGDIR"
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log}"

echo_log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
err_log(){ echo "[$(date +%H:%M:%S)] ERROR: $*" | tee -a "$LOGFILE" >&2; }

is_root(){ [[ "$(id -u)" == "0" ]]; }
run_sudo(){
  if is_root; then bash -c "$*"; else sudo bash -c "$*"; fi
}

# generic binary check (path + common alt locations)
is_installed_bin(){
  local bin="$1"
  if command -v "$bin" >/dev/null 2>&1; then return 0; fi
  local paths=( "/usr/local/bin" "/usr/bin" "$HOME/.local/bin" "$HOME/go/bin" "/snap/bin" )
  for p in "${paths[@]}"; do
    [ -x "$p/$bin" ] && return 0
  done
  return 1
}

# try to get version, with heuristics
get_version(){
  local bin="$1"
  # try common flags
  for flag in "--version" "-v" "-V" "version"; do
    if command -v "$bin" >/dev/null 2>&1; then
      out="$($bin $flag 2>/dev/null || true)"
      if [ -n "$out" ]; then
        # first line only
        echo "$out" | head -n1
        return 0
      fi
    fi
  done
  echo "unknown"
  return 1
}

# simple semver compare helper (major.minor.patch) - returns 0 if a>=b
ver_ge(){
  # usage: ver_ge "1.2.3" "1.2.0" && echo yes
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
