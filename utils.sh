#!/usr/bin/env bash
# ~/alltools/utils.sh — universal helper for alltools project
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -euo pipefail

# === Logging Setup ===
LOGDIR="${LOGDIR:-$SCRIPT_ROOT/install_logs}"
mkdir -p "$LOGDIR"
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log}"

echo_log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
err_log(){ echo "[$(date +%H:%M:%S)] ERROR: $*" | tee -a "$LOGFILE" >&2; }

# === Root Helpers ===
is_root(){ [[ "$(id -u)" == "0" ]]; }
run_sudo(){
  if is_root; then bash -c "$*"; else sudo bash -c "$*"; fi
}

# === Optimized Binary Check ===
is_installed_bin(){
  local bin="${1:-}"
  if [[ -z "$bin" ]]; then return 1; fi
  command -v "$bin" >/dev/null 2>&1 && return 0
  local gopath; gopath="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
  local p
  for p in "/usr/local/bin" "/usr/bin" "$HOME/.local/bin" "$gopath/bin" "/snap/bin"; do
    [[ -x "$p/$bin" ]] && return 0
  done
  return 1
}

# === Fast get_version (non-blocking + safe mode) ===
# Usage: get_version <binary-name>
# Returns first non-empty line of version output, or "unknown"
get_version(){
  local bin="${1:-}"
  if [[ -z "$bin" ]]; then
    echo "unknown"
    return 1
  fi

  local exe out flag
  local TO=2  # seconds timeout, tweak if needed

  exe="$(command -v "$bin" 2>/dev/null || echo "$bin")"

  # Special cases: some tools print helpful info with -h (and hang on --version)
  case "$bin" in
    httprobe|gobuster)
      out="$(timeout ${TO}s "$exe" -h 2>/dev/null | head -n1 || true)"
      if [[ -n "$out" ]]; then
        echo "$out" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
        return 0
      fi
      ;;
  esac

  # Try common version flags (avoid blocking)
  for flag in "--version" "-v" "-V" "version"; do
    out="$(timeout ${TO}s "$exe" "$flag" 2>/dev/null | head -n1 || true)"
    if [[ -n "$out" ]]; then
      echo "$out" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
      return 0
    fi
  done

  # Last resort: run program without args (some print version/info)
  out="$(timeout ${TO}s "$exe" 2>/dev/null | head -n1 || true)"
  if [[ -n "$out" ]]; then
    echo "$out" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
    return 0
  fi

  echo "unknown"
  return 1
}

# === Semver Compare Helper (a >= b) ===
ver_ge(){
  if [[ -z "${1:-}" || -z "${2:-}" ]]; then return 1; fi
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

# === Quick summary display ===
quick_summary(){
  local total="${1:-0}" found="${2:-0}"
  if [[ "$total" -eq 0 ]]; then
    echo_log "Summary: 0/0 tools"
    return
  fi
  local pct=$(( found * 100 / total ))
  local color
  if (( pct < 70 )); then color="\e[31m"
  elif (( pct < 90 )); then color="\e[33m"
  else color="\e[32m"; fi
  echo -e "[$(date +%H:%M:%S)] Summary: ${color}${found}/${total} tools OK (${pct}%)\e[0m" | tee -a "$LOGFILE"
}

# === Generic retry wrapper ===
retry(){
  local max="${1:-3}"; shift
  local count=0
  until "$@"; do
    count=$((count+1))
    if (( count >= max )); then
      err_log "Command failed after ${max} attempts: $*"
      return 1
    fi
    echo_log "Retry $count/$max: $*"
    sleep 2
  done
}

# === Downloader helper (curl/wget/aria2c auto) ===
fetch_file(){
  local url="${1:-}" dest="${2:-}"
  if [[ -z "$url" || -z "$dest" ]]; then
    err_log "fetch_file requires <url> <dest>"
    return 1
  fi
  if command -v aria2c >/dev/null 2>&1; then
    aria2c -x 8 -s 8 -k 1M -o "$dest" "$url" >>"$LOGFILE" 2>&1
  elif command -v curl >/dev/null 2>&1; then
    curl -L -o "$dest" "$url" >>"$LOGFILE" 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$dest" "$url" >>"$LOGFILE" 2>&1
  else
    err_log "No download tool found (need curl/wget/aria2c)"
    return 1
  fi
}

# EOF
