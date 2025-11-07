#!/usr/bin/env bash
#
# setup.sh - Installer untuk autohunt + tools eksternal + wordlists/payloads
#
# Fitur:
# - Build binary autohunt dari source (Go)
# - Install tools eksternal pendukung (opsional tapi direkomendasikan):
#     - gau
#     - waybackurls
#     - subfinder
#     - httpx
#     - ffuf
# - Download dan setup wordlist/payload fuzzing terkurasi (berbasis SecLists, tidak full):
#     - Wordlist direktori & file sensitif
#     - Wordlist endpoint umum
#     - Payload XSS umum dan efektif
# - Copy binary ke /usr/bin (atau /data/data/com.termux/files/usr/bin untuk Termux)
#
# Catatan:
# - Wajib dijalankan dengan hak yang cukup untuk menulis ke direktori bin sistem:
#     - Linux/macOS: gunakan sudo jika perlu
# - Script ini mencoba deteksi environment (Linux/macOS/Termux).
# - Tools eksternal & wordlists hanya diinstall jika memungkinkan.
#
# Penggunaan:
#   chmod +x setup.sh
#   ./setup.sh
#
# Setelah selesai:
#   autohunt -h
#   autohunt -u https://target.com -v
#

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_NAME="autohunt"

# Warna sederhana
RED="$(printf '\033[31m')"
GREEN="$(printf '\033[32m')"
YELLOW="$(printf '\033[33m')"
BLUE="$(printf '\033[34m')"
RESET="$(printf '\033[0m')"

log_info()  { printf "${BLUE}[INFO]${RESET} %s\n" "$*"; }
log_warn()  { printf "${YELLOW}[WARN]${RESET} %s\n" "$*"; }
log_error() { printf "${RED}[ERROR]${RESET} %s\n" "$*"; }
log_ok()    { printf "${GREEN}[OK]${RESET} %s\n" "$*"; }

detect_env() {
  # Deteksi apakah Termux
  if [ -n "${PREFIX-}" ] && [ -d "$PREFIX" ] && echo "$PREFIX" | grep -qi "com.termux"; then
    echo "termux"
    return
  fi

  # Deteksi OS lain
  local uname_s
  uname_s="$(uname -s 2>/dev/null || echo "")"
  case "$uname_s" in
    Linux*) echo "linux" ;;
    Darwin*) echo "darwin" ;;
    *) echo "unknown" ;;
  esac
}

ensure_go() {
  if command -v go >/dev/null 2>&1; then
    log_ok "Go sudah terinstall: $(go version)"
    return 0
  fi

  log_warn "Go tidak ditemukan di PATH."
  log_warn "Silakan install Go manual sesuai OS kamu, contoh:"
  log_warn "  Linux   : sudo apt install golang-go"
  log_warn "  Termux  : pkg install golang"
  log_warn "  macOS   : brew install go"
  log_warn "  Windows : install dari https://go.dev/dl/ (untuk WSL: apt install golang-go)"
  return 1
}

build_autohunt() {
  log_info "Membangun binary autohunt..."
  cd "$PROJECT_ROOT"

  if ! go build -o "$BIN_NAME" ./cmd/autohunt; then
    log_error "Gagal build autohunt. Periksa error di atas."
    exit 1
  fi

  log_ok "Binary autohunt berhasil dibangun: $PROJECT_ROOT/$BIN_NAME"
}

install_binary_global() {
  local env_type dest

  env_type="$(detect_env)"
  case "$env_type" in
    termux)
      dest="$PREFIX/bin/$BIN_NAME"
      ;;
    linux|darwin)
      # Default ke /usr/bin, jika tidak bisa tulis, coba /usr/local/bin
      if [ -w /usr/bin ] || [ "$(id -u)" -eq 0 ]; then
        dest="/usr/bin/$BIN_NAME"
      else
        dest="/usr/local/bin/$BIN_NAME"
      fi
      ;;
    *)
      log_warn "OS tidak dikenali. Binary tidak akan dicopy global."
      log_warn "Kamu bisa menjalankan langsung dari: $PROJECT_ROOT/$BIN_NAME"
      return 0
      ;;
  esac

  log_info "Menginstall autohunt ke: $dest"
  if cp "$PROJECT_ROOT/$BIN_NAME" "$dest"; then
    chmod +x "$dest" || true
    log_ok "autohunt terinstall global sebagai: $dest"
  else
    log_error "Gagal copy ke $dest. Coba jalankan dengan sudo atau copy manual:"
    log_error "  sudo cp $PROJECT_ROOT/$BIN_NAME /usr/local/bin/$BIN_NAME"
    exit 1
  fi
}

install_go_tool() {
  # $1 = package path (go install ...)
  # $2 = binary name (untuk cek di PATH)
  local pkg="$1"
  local bin_name="$2"

  if command -v "$bin_name" >/dev/null 2>&1; then
    log_ok "External tool '$bin_name' sudah terinstall."
    return 0
  fi

  if ! command -v go >/dev/null 2>&1; then
    log_warn "Go tidak tersedia, skip install $bin_name ($pkg)."
    return 1
  fi

  log_info "Menginstall external tool '$bin_name' dari '$pkg'..."
  # Untuk Go 1.21+, gunakan 'go install pkg@latest'
  if go install "${pkg}@latest"; then
    if command -v "$bin_name" >/dev/null 2>&1; then
      log_ok "'$bin_name' berhasil diinstall dan tersedia di PATH."
      return 0
    fi

    # Jika GOPATH/bin tidak di PATH, tampilkan info
    local gopath
    gopath="$(go env GOPATH 2>/dev/null || echo "")"
    if [ -n "$gopath" ] && [ -x "$gopath/bin/$bin_name" ]; then
      log_warn "'$bin_name' terinstall di $gopath/bin tetapi belum ada di PATH."
      log_warn "Tambahkan ke PATH, contoh:"
      log_warn "  export PATH=\"\$PATH:$gopath/bin\""
      return 0
    fi

    log_warn "Install '$bin_name' selesai tapi tidak ditemukan di PATH. Cek konfigurasi GOPATH/GOBIN."
  else
    log_warn "Gagal go install '$pkg'."
    return 1
  fi
}

install_external_tools() {
  log_info "Menginstall tools eksternal yang direkomendasikan (jika memungkinkan)..."

  # gau - URL collection dari berbagai sumber (wayback-style)
  install_go_tool "github.com/lc/gau/v2/cmd/gau" "gau" || true

  # waybackurls - URL collection dari Wayback Machine
  install_go_tool "github.com/tomnomnom/waybackurls" "waybackurls" || true

  # subfinder - subdomain enumeration
  install_go_tool "github.com/projectdiscovery/subfinder/v2/cmd/subfinder" "subfinder" || true

  # httpx - HTTP probing / live host checker
  install_go_tool "github.com/projectdiscovery/httpx/cmd/httpx" "httpx" || true

  # ffuf - directory/file fuzzing (digunakan untuk brute path sensitif, jika diintegrasikan)
  install_go_tool "github.com/ffuf/ffuf" "ffuf" || true

  log_info "Selesai mencoba install tools eksternal."
  log_info "autohunt akan otomatis memakai tools yang tersedia di PATH (gau, waybackurls, subfinder, httpx, ffuf) sesuai integrasi yang ada."
}

install_wordlists_and_payloads() {
  log_info "Mengatur direktori wordlists & payloads untuk autohunt..."

  AUTOWL_DIR="$PROJECT_ROOT/wordlists"
  mkdir -p "$AUTOWL_DIR"

  # 1. Wordlist direktori & file sensitif (subset terkurasi dari SecLists)
  # Sumber referensi:
  # - https://github.com/danielmiessler/SecLists/tree/master/Discovery/Web-Content
  # - https://github.com/danielmiessler/SecLists/tree/master/Discovery/Web-Content/common.txt
  # Di sini kita buat subset bawaan yang ringan namun efektif.
  SENSITIVE_WORDLIST="$AUTOWL_DIR/dirs_common.txt"
  if [ ! -f "$SENSITIVE_WORDLIST" ]; then
    cat > "$SENSITIVE_WORDLIST" << 'EOF'
/
admin
admin/
admin/login
adminpanel
administrator
api
api/
backup
backup/
backups
config
config.php
config.bak
database.sql
db.sql
debug
dev
env
login
login.php
old
old/
panel
phpinfo.php
robots.txt
server-status
shell.php
staging
test
test/
uploads
uploads/
EOF
    log_ok "Wordlist direktori/file sensitif dibuat: $SENSITIVE_WORDLIST"
  else
    log_info "Wordlist $SENSITIVE_WORDLIST sudah ada, skip."
  fi

  # 2. Wordlist endpoint parameter umum (untuk modul XSS/SQLi/LFI, subset)
  PARAM_WORDLIST="$AUTOWL_DIR/params_common.txt"
  if [ ! -f "$PARAM_WORDLIST" ]; then
    cat > "$PARAM_WORDLIST" << 'EOF'
id
ids
uid
user
userid
username
page
p
q
s
search
query
cat
category
ref
url
next
redir
redirect
return
dest
file
path
include
view
template
EOF
    log_ok "Wordlist parameter umum dibuat: $PARAM_WORDLIST"
  else
    log_info "Wordlist $PARAM_WORDLIST sudah ada, skip."
  fi

  # 3. Payload XSS terkurasi (berdasarkan ide dari SecLists/Fuzzing/XSS but subset)
  XSS_PAYLOADS="$AUTOWL_DIR/xss_payloads.txt"
  if [ ! -f "$XSS_PAYLOADS" ]; then
    cat > "$XSS_PAYLOADS" << 'EOF'
"><svg/onload=alert(1)>
"><img src=x onerror=alert(1)>
"><script>alert(1)</script>
"><script>confirm(1)</script>
"><script>prompt(1)</script>
"><body onload=alert(1)>
"><iframe src=javascript:alert(1)>
"><svg><script>alert(1)</script>
"><img src=x: onerror=alert(1)>
"><details open ontoggle=alert(1)>
" autofocus onfocus=alert(1) x="
'"><svg/onload=alert(1)>
'"><img src=x onerror=alert(1)>
'"><script>alert(1)</script>
</script><script>alert(1)</script>
"><svg/onload=alert(document.domain)>
"><img src=x onerror=alert(document.domain)>
EOF
    log_ok "Payload XSS terkurasi dibuat: $XSS_PAYLOADS"
  else
    log_info "Payload XSS $XSS_PAYLOADS sudah ada, skip."
  fi

  # 4. Wordlist kecil untuk SSRF/Redirect (target aman)
  SSRF_WORDLIST="$AUTOWL_DIR/ssrf_targets.txt"
  if [ ! -f "$SSRF_WORDLIST" ]; then
    cat > "$SSRF_WORDLIST" << 'EOF'
http://127.0.0.1/
http://localhost/
http://0.0.0.0/
EOF
    log_ok "Wordlist SSRF kecil dibuat: $SSRF_WORDLIST"
  else
    log_info "Wordlist $SSRF_WORDLIST sudah ada, skip."
  fi

  log_ok "Wordlists & XSS payloads siap. Modul autohunt dapat disinkronkan membaca dari direktori: $AUTOWL_DIR"
  log_info "Pastikan versi autohunt terbaru menggunakan path wordlists ini untuk fuzzing terarah."
}

main() {
  log_info "Menjalankan setup autohunt..."

  if ! ensure_go; then
    log_error "Go wajib terinstall untuk build autohunt. Setup dihentikan."
    exit 1
  fi

  build_autohunt
  install_binary_global
  install_external_tools
  install_wordlists_and_payloads

  log_ok "Setup selesai."
  log_info "Contoh penggunaan:"
  log_info "  autohunt -u https://target.com --fullpower -c 20 -v"
  log_info "  autohunt -u https://target.com --fullpower-aggressive -c 40 -v   # disarankan di VPS"
}

main "$@"
