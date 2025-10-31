#!/usr/bin/env bash
# install.sh (main)
set -euo pipefail
cd "$(dirname "$0")"

export LOGDIR="$(pwd)/install_logs"
mkdir -p "$LOGDIR"
export LOGFILE="$LOGDIR/install_$(date +%Y%m%d_%H%M%S).log"

# source utils (PASTIKAN ini menunjuk ke folder modules)
source modules/utils.sh

echo_log "Start master installer (one command). Logs -> $LOGFILE"
echo_log "Running modules..."

# run modules (each module logs to LOGFILE via utils)
source modules/setup-apt.sh
install_or_upgrade_apt

source modules/setup-snap.sh
# installs feroxbuster/amass if needed

source modules/setup-go.sh
install_or_update_go_tools

source modules/setup-python.sh
# pipx + sublist3r

source modules/setup-xray.sh
# xray manual installer

# final checks
source modules/check-tools.sh

echo_log "DONE. Cek logs -> $LOGFILE"
echo "Jika mau lihat summary ringkas: cat $LOGFILE | tail -n 200"
