#!/usr/bin/env bash
# ==============================================================================
#               BUG.x Uninstaller Script
# ==============================================================================
#
# -- WARNING --
# 1. This script removes all generated files and directories by setup.sh.
# 2. It does NOT remove system-wide packages (APT, Go binaries) by default.
# 3. Use the --force flag to attempt system-wide removal.
#
# ==============================================================================

set -Eeuo pipefail

readonly PROJECT_DIR="$HOME/BUGx"
readonly C_YELLOW="\033[1;33m" C_RED="\033[1;31m" C_RESET="\033[0m"

info()    { echo -e "[INFO]  $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
header()  { echo -e "\n\033[1m--- $S* ---\033[0m"; }

header "Memulai Proses Pembersihan BUG.x"

info "Menghapus direktori buatan setup.sh..."
rm -rf "$PROJECT_DIR/bin"
rm -rf "$PROJECT_DIR/tools"
rm -rf "$PROJECT_DIR/logs"
rm -rf "$PROJECT_DIR/wordlists"
rm -rf "$PROJECT_DIR/help_output"
rm -rf "$PROJECT_DIR/tmp"
info "Direktori proyek telah dibersihkan."

if [[ "${1:-}" == "--force" ]]; then
    warn "Opsi --force terdeteksi. Mencoba menghapus paket sistem..."
    info "CATATAN: Ini akan meminta password sudo untuk menghapus paket APT."
    
    # Define tools to remove again, as this script is standalone
    readonly APT_TOOLS=(arjun wfuzz sqlmap masscan)
    readonly GO_TOOLS_TO_CLEAN=(dalfox ffuf gau getJS gf subjack subjs aquatone gitleaks) # etc.
    
    header "Menghapus Paket APT"
    sudo apt-get remove --purge -y "${APT_TOOLS[@]}" || warn "Beberapa paket APT mungkin gagal dihapus atau tidak terinstal."
    
    header "Menghapus Binaries Go"
    for tool in "${GO_TOOLS_TO_CLEAN[@]}"; do
        rm -f "$(go env GOBIN)/$tool"
    done
    info "Selesai mencoba menghapus binaries Go."
else
    warn "Menjalankan dalam mode aman. Paket sistem tidak dihapus."
    warn "Untuk menghapus paket sistem (APT, Go binaries), jalankan: $0 --force"
fi

header "Pembersihan Selesai"
info "File yang dipertahankan: setup.sh, delete.sh, activate.sh, README.md, .git/"
info "Untuk menyelesaikan, refresh shell Anda dengan menjalankan:"
echo -e "  ${C_YELLOW}hash -r && exec bash${C_RESET}"

