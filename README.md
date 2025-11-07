

```project/autohunt/README.md#L1-260
# autohunt

`autohunt` adalah automated recon & vulnerability scanner yang dirancang untuk alur bug bounty modern:

- Satu input target ⇒ pipeline penuh:
  1. Target normalization
  2. Full recon (internal + optional external tools)
  3. URL collection (wayback-style)
  4. Live filtering (httpx-style)
  5. Parameter classification (gf-style)
  6. Vulnerability scanning (XSS, misconfig, sensitive files, dll)
  7. JSON report

Fokus:
- Membantu hunter melakukan coverage luas dan cepat.
- Memanfaatkan kombinasi:
  - Recon pintar
  - Klasifikasi endpoint
  - Scan yang relatif aman (non-destructive, error-based, reflective, misconfig)
- Mudah di-extend (modular, pakai `ScanContext`).

CATATAN:
- Tool ini tidak menjamin 100% temuan bug.
- Target “90%” di sini adalah coverage tinggi untuk kelas bug yang bisa discan otomatis, bukan business logic/complex auth bug.
- Gunakan hanya pada target yang LEGAL (program bug bounty atau milik sendiri).

---

## Fitur Utama

1. Full Recon Pipeline
   - `FullRecon`:
     - Basic HTTP recon:
       - Status hidup/mati
       - Status code
       - Header penting (`Server`, `X-Powered-By`)
       - Tech hints (WordPress, Drupal, dll)
     - URL Pool:
       - Internal crawler (`CrawlBasic`)
       - Path umum: `/login`, `/admin`, `/api`, `/search`, `/dashboard`, dll.
       - Optional external:
         - `gau` / `waybackurls` (jika terinstal, dipanggil otomatis)
     - Live filter:
       - Hanya simpan URL dengan status menarik (200/201/202/301/302/403)
     - Parameter classification (gf-style):
       - Bucket `SQLi`, `XSS`, `LFI`, `OpenRedirect`, `SSRF`

2. ScanContext-based Modules
   - Semua modul membaca dari satu `ScanContext`:
     - Tidak perlu masing-masing re-crawl.
   - Saat ini termasuk:
     - `SensitiveFilesContextModule`
       - Cek `.git/config`, `.env`, `backup.sql`, dll.
     - `DirListingContextModule`
       - Cek directory listing di beberapa path.
     - `SecurityHeadersContextModule`
       - Cek header hardening penting.
     - `CORSContextModule`
       - Cek CORS wildcard / kredensial.
     - `XSSReflectContextModule`
       - Targeted XSS checks:
         - Pakai bucket XSS dari recon.
         - Fallback ke live URLs.
         - Payload aman, cek refleksi + encoding.

3. Modular dan Extendable
   - Core:
     - `ScanContext`, `FullRecon`, `ClassifyParams`
   - Modul mudah ditambah:
     - SQLi (context-based)
     - LFI (context-based)
     - Open Redirect
     - SSRF
     - CVE fingerprint per teknologi
     - ffuf integration (directory brute)

---

## Instalasi

### 1. Prasyarat

Wajib:
- Go 1.21+ (untuk build)
- Akses internet (untuk scan target)

Opsional (untuk “fullpower” ekstra):
- [`gau`](https://github.com/lc/gau) atau [`waybackurls`](https://github.com/tomnomnom/waybackurls)
  - Untuk koleksi URL historical.
- Tools lain yang bisa ditambahkan kemudian:
  - `subfinder`, `httpx`, `ffuf`, dll (belum di-wire penuh di versi ini, tapi arsitektur disiapkan).

### 2. Clone & Build

Clone repo (nanti setelah kamu upload):

```bash
git clone https://github.com/<username>/autohunt.git
cd autohunt
go build -o autohunt ./cmd/autohunt
```

Command di atas menghasilkan binary:
- `./autohunt` (Linux/macOS/Termux)
- Di Windows:
  - `go build -o autohunt.exe ./cmd/autohunt`

---

## Cara Pakai

Basic:

```bash
# Single target (domain atau URL)
./autohunt -u https://target.com

# Verbose (lihat setiap stage & modul)
./autohunt -u target.com -v

# Multiple targets dari file
./autohunt -f targets.txt -v

# Atur timeout global (detik)
./autohunt -u target.com -timeout 900 -v
```

Default:
- `-fullpower` = true
  - Mengaktifkan:
    - FullRecon
    - URL pool
    - Live filter
    - Param buckets
    - Optional gau/waybackurls jika tersedia

Output:
- `autohunt_result.json`
  - Berisi list temuan:
    - `target`
    - `endpoint`
    - `module`
    - `type`
    - `severity`
    - `confidence`
    - `evidence`
    - `tags`

---

## Instalasi di Berbagai Lingkungan

### Linux / VPS

```bash
sudo apt update
sudo apt install -y golang-go

git clone https://github.com/<username>/autohunt.git
cd autohunt
go build -o autohunt ./cmd/autohunt

# optional: tambah ke PATH
sudo cp autohunt /usr/local/bin/autohunt
```

Run:

```bash
autohunt -u https://target.com -v
```

### Termux (Android)

```bash
pkg update
pkg install -y golang git

git clone https://github.com/<username>/autohunt.git
cd autohunt
go build -o autohunt ./cmd/autohunt
```

Run:

```bash
./autohunt -u https://target.com -v
```

### macOS

```bash
brew install go git

git clone https://github.com/<username>/autohunt.git
cd autohunt
go build -o autohunt ./cmd/autohunt
```

Run:

```bash
./autohunt -u https://target.com -v
```

### Windows (PowerShell)

1. Install Go dari https://go.dev/dl/
2. Clone repo:

```powershell
git clone https://github.com/<username>/autohunt.git
cd autohunt
go build -o autohunt.exe ./cmd/autohunt
.\autohunt.exe -u https://target.com -v
```

---

## Struktur Project (Ringkas)

```text
cmd/autohunt/main.go          # CLI & pipeline stages
internal/core/types.go        # Target, Finding, Module, ContextModule
internal/core/context.go      # ScanContext & buckets
internal/core/recon.go        # ReconBasic
internal/core/crawler.go      # CrawlBasic
internal/core/fullrecon.go    # FullRecon, URLPool, Live filter, ClassifyParams
internal/core/report.go       # SaveFindingsJSON
internal/core/targets.go      # LoadTargets & normalizeURL

internal/modules/             # All modules (legacy + ContextModule)
  senstive_file.go            # SensitiveFilesModule + SensitiveFilesContextModule
  dir_listing.go              # DirListingModule + DirListingContextModule
  security_headers.go         # SecurityHeadersModule + SecurityHeadersContextModule
  moodules.go                 # CORSModule + CORSContextModule
  xss_reflect.go              # XSSReflectModule + XSSReflectContextModule
  sqli_error.go               # (legacy SQLi module, can be upgraded to context)
  lfi_basic.go                # (legacy LFI module)
  cve_fingerprint.go          # (legacy CVE fingerprinting)
