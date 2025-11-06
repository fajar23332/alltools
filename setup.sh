#!/usr/bin/env bash
# ==============================================================================
#
# ██████╗ ██╗   ██╗  ██████╗    ██╗  ██╗
# ██╔══██╗██║   ██║ ██╔════╝    ██║ ██╔╝
# ██████╔╝██║   ██║ ██║  ███╗   █████╔╝
# ██╔══██╗██║   ██║ ██║   ██║   ██╔═██╗
# ██████╔╝╚██████╔╝ ╚██████╔╝██╗██║  ██╗
# ╚═════╝  ╚═════╝   ╚═════╝ ╚═╝╚═╝  ╚═╝
#
#                       BUG.x Setup Orchestrator
#
# ==============================================================================
#
# -- IMPORTANT ASSERTIONS --
# 1. This script is designed to be self-contained within the ~/BUGx directory.
# 2. System package modifications (apt) require sudo and will be logged.
# 3. All file operations are restricted to this project's directory, with
#    explicit exceptions for user-config files (~/.gf, ~/.gau.toml).
#
# ==============================================================================

set -Eeuo pipefail

# --- Configuration and Constants ---
readonly PROJECT_DIR="$HOME/BUGx"
readonly BIN_DIR="$PROJECT_DIR/bin"
readonly TOOLS_DIR="$PROJECT_DIR/tools"
readonly LOGS_DIR="$PROJECT_DIR/logs"
readonly WORDLISTS_DIR="$PROJECT_DIR/wordlists"
readonly HELP_DIR="$PROJECT_DIR/help_output"
readonly TMP_DIR="$PROJECT_DIR/tmp"

# --- Tool Lists ---
# Only install tools that are actually used by run.py
readonly APT_TOOLS=(arjun sqlmap)
readonly PDTM_TOOLS=(subfinder httpx katana nuclei)
readonly GO_INSTALL_MANUAL_TOOLS=(dalfox ffuf gau gf subjack kxss)
readonly BUILD_TOOLS=(gf-patterns)

# --- Wordlist Definitions ---
# Associative array mapping category to a space-separated list of URLs
declare -A WORDLIST_CATEGORIES
WORDLIST_CATEGORIES=(
    [xss]="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/XSS/XSS-Jhaddix.txt https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/XSS/XSS-OFJAAAH.txt"
    [sqli]="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/SQLi/Generic-SQLi.txt https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/SQLi/sqli-errors.txt"
    [fuzzing]="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/special-chars.txt https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/common-http-headers.txt"
    [discovery]="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/common.txt https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/directory-list-2.3-medium.txt"
    [params]="https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/burp-parameter-names.txt"
)

# --- UI & Logging Helpers ---
readonly C_BLUE="\033[1;34m" C_GREEN="\033[1;32m" C_YELLOW="\033[1;33m" C_RED="\033[1;31m" C_BOLD="\033[1m" C_RESET="\033[0m"
readonly LOG_FILE="$LOGS_DIR/setup.log"
readonly ERROR_LOG="$LOGS_DIR/setup-error.log"

# Appends to log file
log()     { echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] [LOG]   $*" >> "$LOG_FILE"; }
info()    { echo -e "${C_BLUE}[INFO]${C_RESET}  $*"; log "[INFO]  $*"; }
ok()      { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; log "[OK]    $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; log "[WARN]  $*"; }
err()     { echo -e "${C_RED}[ERROR]${C_RESET} $*"; echo "[ERROR] $*" >> "$ERROR_LOG"; log "[ERROR] $*"; }
step()    { echo -e "\n${C_BOLD}>>> $*${C_RESET}"; log ">>> $*"; }
divider() { echo -e "${C_BLUE}======================================================================${C_RESET}"; }

# --- State Arrays ---
INSTALLED=() SKIPPED=() FAILED=() HELP_FAILED=()

# --- Core Functions ---

print_banner() {
    cat << "EOF"

██████╗ ██╗   ██╗  ██████╗    ██╗  ██╗
██╔══██╗██║   ██║ ██╔════╝    ██║ ██╔╝
██████╔╝██║   ██║ ██║  ███╗   █████╔╝
██╔══██╗██║   ██║ ██║   ██║   ██╔═██╗
██████╔╝╚██████╔╝ ╚██████╔╝██╗██║  ██╗
╚═════╝  ╚═════╝   ╚═════╝ ╚═╝╚═╝  ╚═╝

EOF
    echo -e "            ${C_BOLD}BUG.x Setup Orchestrator${C_RESET}"
    divider
}

init_dirs() {
    mkdir -p "$BIN_DIR" "$TOOLS_DIR" "$LOGS_DIR" "$WORDLISTS_DIR" "$HELP_DIR" "$TMP_DIR"
    : > "$LOG_FILE"
    : > "$ERROR_LOG"
    info "Direktori proyek telah disiapkan."
}

command_exists() {
    command -v "$1" &>/dev/null
}

# --- Installation Logic ---

install_pdtm() {
    step "Memeriksa instalasi pdtm..."
    if command_exists pdtm; then
        ok "pdtm sudah terinstal."
        return 0
    fi
    info "pdtm tidak ditemukan. Menginstal..."
    if ! go install -v github.com/projectdiscovery/pdtm/cmd/pdtm@latest &>> "$LOG_FILE"; then
        err "Gagal menginstal pdtm. Pastikan Go sudah terinstal dan PATH sudah benar. Akan mencoba menginstal tools PDTM secara manual."
        FAILED+=("pdtm")
        return 1 # Tetap return 1 untuk menandakan pdtm gagal diinstal
    fi
    ok "pdtm berhasil diinstal."
}

install_apt_tools() {
    step "Memulai instalasi tools via APT..."
    if ! command_exists apt; then
        warn "Perintah 'apt' tidak ditemukan. Melewatkan instalasi tools APT."
        return
    fi

    info "Memeriksa status DPKG/APT..."
    if dpkg --audit 2>/dev/null | grep -q .; then
        warn "Inkonsistensi DPKG terdeteksi. Mencoba perbaikan otomatis..."
        sudo dpkg --configure -a &>> "$LOG_FILE"
        sudo apt --fix-broken install -y &>> "$LOG_FILE"
        ok "Perbaikan otomatis APT selesai."
    fi

    for tool in "${APT_TOOLS[@]}"; do
        if command_exists "$tool"; then
            ok "$tool sudah terinstal (dilewati)."
            SKIPPED+=("$tool")
        else
            info "Menginstal $tool via APT..."
            if sudo apt-get install -y "$tool" &>> "$LOG_FILE"; then
                ok "$tool berhasil diinstal."
                INSTALLED+=("$tool")
            else
                err "Gagal menginstal $tool."
                FAILED+=("$tool")
            fi
        fi
    done
}

install_pdtm_tools() {
    step "Memulai instalasi tools via pdtm..."
    if ! command_exists pdtm; then
        warn "pdtm tidak ditemukan atau gagal diinstal. Mencoba menginstal tools PDTM secara manual satu per satu."
        for tool in "${PDTM_TOOLS[@]}"; do
            info "Menginstal $tool secara manual via 'go install'..."
            local pkg_path
            case $tool in
                aix) pkg_path="github.com/projectdiscovery/aix/cmd/aix" ;;
                alterx) pkg_path="github.com/projectdiscovery/alterx/cmd/alterx" ;;
                asnmap) pkg_path="github.com/projectdiscovery/asnmap/cmd/asnmap" ;;
                cdncheck) pkg_path="github.com/projectdiscovery/cdncheck/cmd/cdncheck" ;;
                cloudlist) pkg_path="github.com/projectdiscovery/cloudlist/cmd/cloudlist" ;;
                dnsx) pkg_path="github.com/projectdiscovery/dnsx/cmd/dnsx" ;;
                httpx) pkg_path="github.com/projectdiscovery/httpx/cmd/httpx" ;;
                interactsh-client) pkg_path="github.com/projectdiscovery/interactsh/cmd/interactsh-client" ;;
                interactsh-server) pkg_path="github.com/projectdiscovery/interactsh/cmd/interactsh-server" ;;
                katana) pkg_path="github.com/projectdiscovery/katana/cmd/katana" ;;
                mapcidr) pkg_path="github.com/projectdiscovery/mapcidr/cmd/mapcidr" ;;
                naabu) pkg_path="github.com/projectdiscovery/naabu/v2/cmd/naabu" ;;
                notify) pkg_path="github.com/projectdiscovery/notify/cmd/notify" ;;
                nuclei) pkg_path="github.com/projectdiscovery/nuclei/v2/cmd/nuclei" ;;
                proxify) pkg_path="github.com/projectdiscovery/proxify/cmd/proxify" ;;
                shuffledns) pkg_path="github.com/projectdiscovery/shuffledns/cmd/shuffledns" ;;
                simplehttpserver) pkg_path="github.com/projectdiscovery/simplehttpserver/cmd/simplehttpserver" ;;
                subfinder) pkg_path="github.com/projectdiscovery/subfinder/v2/cmd/subfinder" ;;
                tldfinder) pkg_path="github.com/projectdiscovery/tldfinder/cmd/tldfinder" ;;
                tlsx) pkg_path="github.com/projectdiscovery/tlsx/cmd/tlsx" ;;
                tunnelx) pkg_path="github.com/projectdiscovery/tunnelx/cmd/tunnelx" ;;
                uncover) pkg_path="github.com/projectdiscovery/uncover/cmd/uncover" ;;
                urlfinder) pkg_path="github.com/projectdiscovery/urlfinder/cmd/urlfinder" ;;
                *)
                    err "Package path tidak diketahui untuk $tool."
                    FAILED+=("$tool")
                    continue
                    ;;
            esac

            if go install -v "$pkg_path@latest" &>> "$LOG_FILE"; then
                ln -sf "$HOME/go/bin/$tool" "$BIN_DIR/$tool"
                ok "$tool berhasil diinstal secara manual."
                INSTALLED+=("$tool")
            else
                err "Gagal menginstal $tool secara manual."
                FAILED+=("$tool")
            fi
        done
        return
    fi

    for tool in "${PDTM_TOOLS[@]}"; do
        if command_exists "$tool"; then
            ok "$tool sudah terinstal (dilewati)."
            SKIPPED+=("$tool")
        else
            info "Menginstal $tool via pdtm..."
            if pdtm -i "$tool" -bp "$BIN_DIR" &>> "$LOG_FILE"; then
                ok "$tool berhasil diinstal."
                INSTALLED+=("$tool")
            else
                err "Gagal menginstal $tool."
                FAILED+=("$tool")
            fi
        fi
    done
}

install_go_manual_tools() {
    step "Memulai instalasi tools via 'go install'..."
    for tool in "${GO_INSTALL_MANUAL_TOOLS[@]}"; do
        if command_exists "$tool"; then
            ok "$tool sudah terinstal (dilewati)."
            SKIPPED+=("$tool")
        else
            info "Menginstal $tool via 'go install'..."
            local pkg_path
            case $tool in
                dalfox) pkg_path="github.com/hahwul/dalfox/v2" ;;
                ffuf) pkg_path="github.com/ffuf/ffuf" ;;
                gau) pkg_path="github.com/lc/gau/v2/cmd/gau" ;;
                getJS) pkg_path="github.com/003random/getJS" ;;
                gf) pkg_path="github.com/tomnomnom/gf" ;;
                subjack) pkg_path="github.com/haccer/subjack" ;;
                subjs) pkg_path="github.com/lc/subjs" ;;
                *)
                    err "Package path tidak diketahui untuk $tool."
                    FAILED+=("$tool")
                    continue
                    ;;
            esac

            if go install -v "$pkg_path@latest" &>> "$LOG_FILE"; then
                # Create symlink to our project bin
                ln -sf "$HOME/go/bin/$tool" "$BIN_DIR/$tool"
                ok "$tool berhasil diinstal."
                INSTALLED+=("$tool")
            else
                err "Gagal menginstal $tool."
                FAILED+=("$tool")
            fi
        fi
    done
}

install_build_tools() {
    step "Memulai instalasi tools dari source (BUILD)..."
    for tool in "${BUILD_TOOLS[@]}"; do
        info "Memproses build untuk: $tool"
        case $tool in
            massdns)
                if command_exists massdns; then
                    ok "massdns sudah terinstal (dilewati)."
                    SKIPPED+=("massdns")
                    continue
                fi
                info "Cloning dan build massdns..."
                if git clone https://github.com/blechschmidt/massdns "$TOOLS_DIR/massdns" &>> "$LOG_FILE"; then
                    if make -C "$TOOLS_DIR/massdns" &>> "$LOG_FILE"; then
                        if sudo make -C "$TOOLS_DIR/massdns" install &>> "$LOG_FILE"; then
                            ok "massdns berhasil di-build dan diinstal."
                            INSTALLED+=("massdns")
                        else
                            err "Gagal 'sudo make install' untuk massdns." && FAILED+=("massdns")
                        fi
                    else
                        err "Gagal 'make' untuk massdns." && FAILED+=("massdns")
                    fi
                else
                    err "Gagal 'git clone' untuk massdns." && FAILED+=("massdns")
                fi
                ;;
            aquatone)
                if command_exists aquatone; then
                    ok "aquatone sudah terinstal (dilewati)."
                    SKIPPED+=("aquatone")
                    continue
                fi
                info "Menginstal aquatone via go install..."
                if go install -v github.com/michenriksen/aquatone@latest &>> "$LOG_FILE"; then
                    ln -sf "$HOME/go/bin/aquatone" "$BIN_DIR/aquatone"
                    ok "aquatone berhasil diinstal."
                    INSTALLED+=("aquatone")
                else
                    err "Gagal menginstal aquatone."
                    FAILED+=("aquatone")
                fi
                ;;
            gitleaks)
                 if command_exists gitleaks; then
                    ok "gitleaks sudah terinstal (dilewati)."
                    SKIPPED+=("gitleaks")
                    continue
                fi
                info "Menginstal gitleaks via go install..."
                if go install -v github.com/gitleaks/gitleaks/v8@latest &>> "$LOG_FILE"; then
                    ln -sf "$HOME/go/bin/gitleaks" "$BIN_DIR/gitleaks"
                    ok "gitleaks berhasil diinstal."
                    INSTALLED+=("gitleaks")
                else
                    err "Gagal menginstal gitleaks."
                    FAILED+=("gitleaks")
                fi
                ;;
            gf-patterns)
                info "Mengunduh Gf-Patterns..."
                if [ -d "$HOME/.gf" ]; then
                    warn "Direktori ~/.gf sudah ada. Pola mungkin sudah ada."
                else
                    mkdir -p "$HOME/.gf"
                fi
                if git clone https://github.com/1ndianl33t/Gf-Patterns "$TMP_DIR/Gf-Patterns" &>> "$LOG_FILE"; then
                    cp "$TMP_DIR/Gf-Patterns/"*.json "$HOME/.gf/"
                    rm -rf "$TMP_DIR/Gf-Patterns"
                    ok "Gf-Patterns berhasil diunduh ke ~/.gf."
                    INSTALLED+=("gf-patterns")
                else
                    err "Gagal mengunduh Gf-Patterns."
                    FAILED+=("gf-patterns")
                fi
                ;;
        esac
    done
}

# --- Post-Install Tasks ---

configure_special_tools() {
    step "Menjalankan konfigurasi khusus..."

    # Create .gau.toml with proper TOML format
    info "Membuat file konfigurasi .gau.toml..."

    # Remove old config if exists to prevent duplication
    if [[ -f "$HOME/.gau.toml" ]]; then
        warn "Removing old .gau.toml..."
        rm -f "$HOME/.gau.toml"
    fi

    cat << 'EOF' > "$HOME/.gau.toml"
# .gau.toml - Konfigurasi untuk GAU (GetAllURLs)
# Dibuat secara otomatis oleh setup.sh

threads = 2
verbose = false
retries = 15
subdomains = false
parameters = false
providers = ["wayback", "commoncrawl", "otx", "urlscan"]
blacklist = ["ttf", "woff", "svg", "png", "jpg"]
json = false

[urlscan]
  apikey = ""

[filters]
  from = ""
  to = ""
  matchstatuscodes = []
  matchmimetypes = []
  filterstatuscodes = []
  filtermimetypes = ["image/png", "image/jpg", "image/svg+xml"]
EOF
    ok "File $HOME/.gau.toml berhasil dibuat dengan format TOML yang benar."

    # Update nuclei templates
    if command_exists nuclei; then
        info "Memperbarui Nuclei Templates..."
        if nuclei -update-templates &>> "$LOG_FILE"; then
            ok "Nuclei templates berhasil diperbarui."
        else
            warn "Gagal memperbarui nuclei templates. Anda bisa coba jalankan 'nuclei -update-templates' manual."
        fi
    fi
}

download_wordlists() {
    step "Mengunduh dan menggabungkan wordlists..."
    for category in "${!WORDLIST_CATEGORIES[@]}"; do
        local urls="${WORDLIST_CATEGORIES[$category]}"
        local merged_file="$WORDLISTS_DIR/${category}.txt"
        info "Memproses kategori wordlist: $category"
        : > "$merged_file" # Create or clear the file

        for url in $urls; do
            local filename; filename=$(basename "$url")
            info "  -> Mengunduh $filename..."
            if curl -sL --retry 2 "$url" >> "$merged_file"; then
                ok "     $filename berhasil diunduh dan digabung."
            else
                warn "     Gagal mengunduh $filename."
            fi
        done

        info "  -> Membersihkan dan deduplikasi ${category}.txt..."
        sort -u -o "$merged_file" "$merged_file"
        ok "Wordlist untuk $category siap di $merged_file."
    done
}

# --- Help Capture ---

run_help_capture() {
    step "Memulai proses capture output --help..."
    info "Output akan disimpan di direktori: $HELP_DIR"

    # Combine all tool lists into one
    local all_tools=("${APT_TOOLS[@]}" "${PDTM_TOOLS[@]}" "${GO_INSTALL_MANUAL_TOOLS[@]}" "${BUILD_TOOLS[@]}")

    for tool in "${all_tools[@]}"; do
        if ! command_exists "$tool"; then
            warn "Melewatkan help capture untuk $tool (tidak terinstal)."
            continue
        fi

        info "Capturing help untuk: $tool"
        local out_file="$HELP_DIR/$tool.txt"
        local success=false

        # Special case for masscan
        if [[ "$tool" == "masscan" ]]; then
            if timeout 5s masscan &> "$out_file"; then
                : # Command ran, now check file content
            fi
        else
            # Try -h first
            if timeout 3s "$tool" -h &> "$out_file"; then
                : # Command ran, now check file content
            # If that fails, try --help
            elif timeout 3s "$tool" --help &> "$out_file"; then
                : # Command ran, now check file content
            fi
        fi

        # Check if the output file is not empty, indicating successful capture
        if [ -s "$out_file" ]; then
            ok "Help untuk $tool berhasil di-capture."
        else
            err "Gagal capture help untuk $tool."
            HELP_FAILED+=("$tool")
        fi
    done
}

# --- Script Generation ---

generate_scripts() {
    step "Membuat skrip activate.sh dan delete.sh..."

    # activate.sh
    cat << 'EOF' > "$PROJECT_DIR/activate.sh"
#!/usr/bin/env bash
# ==============================================================================
#               BUG.x Environment Activation Script
# ==============================================================================
#
# -- INFO --
# 1. This script is auto-generated by setup.sh.
# 2. It prepends the project's binary directory to your PATH.
# 3. It sets a guard to ensure tools are run from within the project folder.
#
# ==============================================================================

# Guard: Ensure the script is sourced from within the project directory.
if [[ "$PWD" != "$HOME/BUGx"* ]]; then
    echo -e "\033[1;31m[ERROR]\033[0m Lingkungan BUG.x hanya boleh diaktifkan dari dalam direktori ~/BUGx."
    return 1
fi

export PATH="$HOME/BUGx/bin:$PATH"
export BUGX_ACTIVE=1

echo -e "\033[1;32m[OK]\033[0m Lingkungan BUG.x telah diaktifkan."
echo -e "     Semua tools di ~/BUGx/bin sekarang ada di PATH Anda."

# Simple deactivate function
deactivate() {
    export PATH=$(echo "$PATH" | sed -e "s|$HOME/BUGx/bin:||")
    unset BUGX_ACTIVE
    unset -f deactivate
    echo -e "\033[1;33m[WARN]\033[0m Lingkungan BUG.x telah dinonaktifkan."
}
EOF

    # delete.sh
    cat << 'EOF' > "$PROJECT_DIR/delete.sh"
#!/usr/bin/env bash
# ==============================================================================
#               BUG.x Cleanup Script
# ==============================================================================
#
# This script removes installed tools and generated files but keeps:
# - setup.sh (for reinstallation)
# - BUGx folder structure
# - Source files (run.py, etc)
#
# ==============================================================================

set -Eeuo pipefail

readonly PROJECT_DIR="$HOME/BUGx"
readonly C_YELLOW="\033[1;33m" C_RED="\033[1;31m" C_GREEN="\033[1;32m" C_RESET="\033[0m"

info()    { echo -e "[INFO]  $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
ok()      { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
header()  { echo -e "\n\033[1m--- $* ---\033[0m"; }

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                   BUG.x Cleanup Script                             ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

info "This will clean up installed tools and temporary files"
warn "Directories to be removed: bin/, tools/, logs/, wordlists/, tmp/, results/"
info "Files to be kept: setup.sh, run.py, activate.sh, delete.sh, *.md"
echo ""
read -p "Continue with cleanup? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
    info "Cleanup cancelled."
    exit 0
fi

header "Starting BUG.x Cleanup"

# Deactivate environment if active
if [[ -n "${BUGX_ACTIVE:-}" ]]; then
    info "Deactivating BUG.x environment..."
    export PATH=$(echo "$PATH" | sed -e "s|$HOME/BUGx/bin:||")
    unset BUGX_ACTIVE
    ok "Environment deactivated"
fi

# Remove installed tools and generated directories
header "Removing Installed Tools and Generated Files"

if [[ -d "$PROJECT_DIR/bin" ]]; then
    info "Removing bin/ directory..."
    rm -rf "$PROJECT_DIR/bin"
    ok "Removed bin/"
fi

if [[ -d "$PROJECT_DIR/tools" ]]; then
    info "Removing tools/ directory..."
    rm -rf "$PROJECT_DIR/tools"
    ok "Removed tools/"
fi

if [[ -d "$PROJECT_DIR/logs" ]]; then
    info "Removing logs/ directory..."
    rm -rf "$PROJECT_DIR/logs"
    ok "Removed logs/"
fi

if [[ -d "$PROJECT_DIR/wordlists" ]]; then
    info "Removing wordlists/ directory..."
    rm -rf "$PROJECT_DIR/wordlists"
    ok "Removed wordlists/"
fi

if [[ -d "$PROJECT_DIR/tmp" ]]; then
    info "Removing tmp/ directory..."
    rm -rf "$PROJECT_DIR/tmp"
    ok "Removed tmp/"
fi

if [[ -d "$PROJECT_DIR/results" ]]; then
    warn "Found results/ directory with scan results"
    read -p "Remove results/ directory? (yes/no): " remove_results
    if [[ "$remove_results" == "yes" ]]; then
        rm -rf "$PROJECT_DIR/results"
        ok "Removed results/"
    else
        info "Kept results/ directory"
    fi
fi

if [[ -d "$PROJECT_DIR/help_output" ]]; then
    info "Removing help_output/ directory..."
    rm -rf "$PROJECT_DIR/help_output"
    ok "Removed help_output/"
fi

# Remove user config files
header "Removing User Config Files"

if [[ -f "$HOME/.gau.toml" ]]; then
    info "Removing ~/.gau.toml..."
    rm -f "$HOME/.gau.toml"
    ok "Removed ~/.gau.toml"
fi

if [[ -d "$HOME/.gf" ]]; then
    warn "Found ~/.gf directory (GF patterns)"
    read -p "Remove ~/.gf directory? (yes/no): " remove_gf
    if [[ "$remove_gf" == "yes" ]]; then
        rm -rf "$HOME/.gf"
        ok "Removed ~/.gf"
    else
        info "Kept ~/.gf directory"
    fi
fi

header "Cleanup Complete"
ok "BUG.x cleanup completed successfully!"
echo ""
info "Kept files:"
echo "  - setup.sh (run this to reinstall tools)"
echo "  - run.py and other source files"
echo "  - activate.sh and delete.sh scripts"
echo "  - Documentation files (*.md)"
echo ""
info "To reinstall tools: cd ~/BUGx && ./setup.sh"
echo ""

EOF

    chmod +x "$PROJECT_DIR/activate.sh" "$PROJECT_DIR/delete.sh"
    ok "Skrip activate.sh dan delete.sh berhasil dibuat."
}

# --- Finalization ---

print_summary() {
    divider
    echo -e "            ${C_BOLD}RINGKASAN SETUP BUG.x${C_RESET}"
    divider

    echo -e "${C_GREEN}Terinstal Berhasil :${C_RESET} ${#INSTALLED[@]}"
    printf "  - %s\n" "${INSTALLED[@]}"

    echo -e "${C_YELLOW}Dilewati (Sudah Ada):${C_RESET} ${#SKIPPED[@]}"
    printf "  - %s\n" "${SKIPPED[@]}"

    if [ ${#FAILED[@]} -gt 0 ]; then
        echo -e "${C_RED}Gagal Diinstal      :${C_RESET} ${#FAILED[@]}"
        printf "  - %s\n" "${FAILED[@]}"
        warn "Beberapa instalasi gagal. Silakan periksa log di $ERROR_LOG untuk detail."
    fi

    if [ ${#HELP_FAILED[@]} -gt 0 ]; then
        echo -e "${C_RED}Gagal Capture Help :${C_RESET} ${#HELP_FAILED[@]}"
        printf "  - %s\n" "${HELP_FAILED[@]}"
    fi

    divider
    ok "Setup Selesai."
    info "Langkah selanjutnya:"
    echo -e "  1. Aktifkan environment: ${C_YELLOW}source activate.sh${C_RESET}"
    echo -e "  2. Jalankan BUG.x: ${C_YELLOW}python3 run.py${C_RESET}"
    echo -e "  3. Pilih mode 11 (AUTO HUNT) untuk one-click bug hunting!"
}

# --- Main Execution ---
main() {
    print_banner
    init_dirs

    # --- Run Installation ---
    install_pdtm
    install_apt_tools
    install_pdtm_tools
    install_go_manual_tools
    install_build_tools

    # --- Post-Install ---
    configure_special_tools
    download_wordlists
    generate_scripts

    # --- Finish ---
    print_summary

    # Final exit code
    if [ ${#FAILED[@]} -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main "$@"
