#!/usr/bin/env bash
#
# setup.sh - Installer untuk autohunt + tools eksternal
#
# Fitur:
# - Build binary autohunt dari source (Go)
# - Install tools eksternal pendukung (opsional tapi direkomendasikan):
#     - gau
#     - waybackurls
#     - subfinder
#     - httpx
#     - ffuf
#     - nuclei
# - Copy binary ke /usr/bin (atau /data/data/com.termux/files/usr/bin untuk Termux), overwrite jika sudah ada
#
# Catatan:
# - Wajib dijalankan dengan hak yang cukup untuk menulis ke direktori bin sistem:
#     - Linux/macOS: gunakan sudo jika perlu
# - Script ini mencoba deteksi environment (Linux/macOS/Termux).
# - Setup TIDAK membuat/mengubah wordlist. Wordlist dibaca langsung dari repository (git clone).
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
      # Jika binary ditemukan di PATH, coba juga copy ke /usr/bin atau /usr/local/bin untuk global access
      copy_external_to_usrbin "$bin_name"
      return 0
    fi

    # Jika GOPATH/bin tidak di PATH, tampilkan info
    local gopath
    gopath="$(go env GOPATH 2>/dev/null || echo "")"
    if [ -n "$gopath" ] && [ -x "$gopath/bin/$bin_name" ]; then
      log_warn "'$bin_name' terinstall di $gopath/bin tetapi belum ada di PATH."
      log_warn "Tambahkan ke PATH, contoh:"
      log_warn "  export PATH=\"\$PATH:$gopath/bin\""
      # Tetap coba copy ke /usr/bin atau /usr/local/bin agar bisa dipanggil dari mana saja
      if [ -x "$gopath/bin/$bin_name" ]; then
        copy_external_to_usrbin "$bin_name" "$gopath/bin/$bin_name"
      fi
      return 0
    fi

    log_warn "Install '$bin_name' selesai tapi tidak ditemukan di PATH. Cek konfigurasi GOPATH/GOBIN."
  else
    log_warn "Gagal go install '$pkg'."
    return 1
  fi
}

copy_external_to_usrbin() {
  # $1 = binary name (mis. gau)
  # $2 = full path ke binary (opsional, jika tidak ada akan dicari via command -v)
  local name="$1"
  local src="${2:-}"

  # Cari src jika belum diberikan
  if [ -z "$src" ]; then
    src="$(command -v "$name" 2>/dev/null || true)"
  fi

  if [ -z "$src" ] || [ ! -x "$src" ]; then
    return 1
  fi

  # Tentukan target global
  local dest=""
  if [ -w /usr/bin ] || [ "$(id -u)" -eq 0 ]; then
    dest="/usr/bin/$name"
  elif [ -w /usr/local/bin ] || [ "$(id -u)" -eq 0 ]; then
    dest="/usr/local/bin/$name"
  fi

  if [ -n "$dest" ]; then
    if cp "$src" "$dest" 2>/dev/null; then
      chmod +x "$dest" || true
      log_ok "Tool eksternal '$name' dicopy ke $dest"
      return 0
    else
      log_warn "Gagal copy '$name' ke $dest. Jalankan setup.sh dengan sudo jika ingin global install."
    fi
  fi

  return 1
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

  # nuclei - template-based vulnerability scanner
  install_go_tool "github.com/projectdiscovery/nuclei/v3/cmd/nuclei" "nuclei" || true

  log_info "Selesai mencoba install tools eksternal."
  log_info "autohunt akan otomatis memakai tools yang tersedia di PATH (gau, waybackurls, subfinder, httpx, ffuf, nuclei) sesuai integrasi yang ada."
}

install_wordlists_and_payloads() {
  log_info "Lewati pembuatan atau download wordlists/payloads; autohunt menggunakan wordlists yang ada di repository."
}

main() {
  log_info "Menjalankan setup autohunt..."
  # Buat konfigurasi default untuk gau jika belum ada (~/.gau.toml)
  GAU_CONFIG="$HOME/.gau.toml"
  if [ ! -f "$GAU_CONFIG" ]; then
    cat > "$GAU_CONFIG" << 'EOF'
threads = 2
verbose = false
retries = 15
subdomains = false
parameters = false
providers = ["wayback","commoncrawl","otx","urlscan"]
blacklist = ["ttf","woff","svg","png","jpg"]
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
    log_ok "Konfigurasi default gau dibuat di $GAU_CONFIG"
  else
    log_info "Konfigurasi gau sudah ada di $GAU_CONFIG, tidak diubah."
  fi

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
