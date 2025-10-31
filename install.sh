#!/usr/bin/env bash
# install.sh (main)
set -euo pipefail
cd "$(dirname "$0")"

# === Load utility functions first ===
source modules/utils.sh

# --- User / Home handling (works when user ran script with sudo) ---
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo "~${REAL_USER}")"
# if running as root directly (no SUDO_USER), REAL_USER=root, REAL_HOME=/root
if [ -z "$REAL_HOME" ] || [ "$REAL_HOME" = "~$REAL_USER" ]; then REAL_HOME="$HOME"; fi

# Use real user's install_logs so pipx/go use sane path
LOGDIR="${LOGDIR:-$REAL_HOME/alltools/install_logs}"
mkdir -p "$LOGDIR"
LOGFILE="${LOGFILE:-$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log}"

echo_log "Running as: $(id -un)  (real user: $REAL_USER, real home: $REAL_HOME)"

export LOGDIR="$(pwd)/install_logs"
mkdir -p "$LOGDIR"
export LOGFILE="$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log"

echo_log "Start master installer (one command). Logs -> $LOGFILE"
echo_log "Running modules..."

# --- Jalankan setiap modul utama ---
source modules/setup-apt.sh
install_or_upgrade_apt

source modules/setup-snap.sh
# installs feroxbuster/amass if needed

source modules/setup-go.sh
install_go_tools

source modules/setup-python.sh
# pipx + sublist3r

source modules/setup-xray.sh
# xray manual installer

# final checks
source modules/check-tools.sh

echo_log "DONE. Cek logs -> $LOGFILE"
echo "Jika mau lihat summary ringkas: cat $LOGFILE | tail -n 200"
