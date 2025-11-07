# autohunt

autohunt adalah automated recon & vulnerability scanner yang dirancang untuk alur bug bounty modern:

- Satu input target ⇒ pipeline penuh:
  1. Target normalization
  2. Full recon (internal + optional external tools)
  3. URL collection (wayback-style)
  4. Live/live-like filtering (httpx-style)
  5. Parameter classification (gf-style)
  6. Vulnerability scanning terarah (XSS, SQLi, LFI, redirect, SSRF heuristics, misconfig, exposed files, dll)
  7. JSON report yang siap kamu validasi

Fokus:
- Membantu hunter melakukan coverage luas dan cepat.
- Menggabungkan:
  - Recon pintar + URL enrichment
  - Klasifikasi endpoint/parameter
  - Scan terarah (berbasis intel, bukan tembak buta)
  - Mode agresif yang kuat tapi tetap non-destructive
- Modular dan mudah di-extend (berbasis `ScanContext` + ContextModule).

CATATAN PENTING:
- autohunt tidak menjamin menemukan 100% bug.
- Target pendekatan tinggi (90%+) diarahkan pada KELAS bug yang:
  - Polanya bisa dideteksi otomatis (misconfig, exposures, injection klasik, dll),
  - BUKAN bug business logic, auth kompleks, race condition, dsb.
- Gunakan HANYA pada target yang legal:
  - Program bug bounty,
  - Aset milik sendiri,
  - Aset yang eksplisit mengizinkan scanning.

Repo resmi:
- https://github.com/D0Lv-1N/autohunt.git

---

## Fitur Utama

### 1. Full Recon Pipeline

`FullReconWithConcurrency` membangun `ScanContext`:

- Basic HTTP recon:
  - Status hidup/mati
  - HTTP status code
  - Header penting (`Server`, `X-Powered-By`)
  - Tech hints (WordPress, Laravel, PHP stack, WAF/CDN, dll)

- URL Pool:
  - Internal crawler (`CrawlBasicWithConcurrency`)
  - Static paths umum:
    - `/`, `/login`, `/admin`, `/api`, `/search`, `/dashboard`, dll.
  - Optional external:
    - `gau` / `waybackurls` (jika terpasang):
      - Menambah historical/archived URLs.

- Live filter (httpx-style internal):
  - Hanya simpan URL dengan status menarik:
    - 200, 201, 202, 301, 302, 403

- Parameter classification (gf-style):
  - Membuat buckets:
    - `SQLi`
    - `XSS`
    - `LFI`
    - `OpenRedirect`
    - `SSRF`

Semua data ini disimpan di `ScanContext` dan dipakai oleh modul-modul vuln.

### 2. ScanContext-based Modules (Fullpower)

Modul membaca dari `ScanContext` (bukan scan buta).

Modul utama (mode fullpower):

- `SensitiveFilesContextModule`
  - Cek:
    - `.git/config`, `.env`, `.env.*`, `backup.sql`, `db.sql`, `config.php.bak`, dsb.
  - Di mode agresif:
    - Gunakan `wordlists/dirs_common.txt` untuk path sensitif tambahan.

- `DirListingContextModule`
  - Cek directory listing di path umum (backup, uploads, files, dll).

- `SecurityHeadersContextModule`
  - Cek:
    - CSP, HSTS, XFO, XCTO, Referrer-Policy, dll.

- `CORSContextModule`
  - Deteksi:
    - `Access-Control-Allow-Origin: *`
    - `*` + `Access-Control-Allow-Credentials: true`
    - Pola insecure CORS lain.

- `XSSReflectContextModule`
  - Targeted reflected XSS:
    - Pakai `Buckets.XSS` dari FullRecon.
    - Fallback ke `LiveURLs`.
  - Payload aman:
    - Dan di mode agresif:
      - Tambah payload dari `wordlists/xss_payloads.txt` (subset terkurasi).
  - Cek:
    - Refleksi langsung,
    - Varian encoding,
    - Confidence score.

- `SQLiErrorContextModule`
  - Pakai `Buckets.SQLi` + heuristik param.
  - Inject payload:
    - `'`, `"`, `' OR 1=1--`, dll (non-destructive).
  - Cek pola error DB (MySQL, MSSQL, Postgres, dll).
  - Output:
    - “Possible SQL Injection (Error-based)” dengan evidence dan confidence.

- `LFIBasicContextModule`
  - Pakai `Buckets.LFI` (+ fallback LiveURLs).
  - Payload traversal ke `/etc/passwd` (multi-depth).
  - Cek pola `/etc/passwd`.
  - Output:
    - LFI Critical jika match.

- `OpenRedirectContextModule`
  - Pakai `Buckets.OpenRedirect`.
  - Set param → `https://example.org` / `https://example.com`.
  - Detect:
    - Redirect keluar domain.
  - Output:
    - Possible Open Redirect.

- `SSRFContextModule` (heuristik aman)
  - Pakai `Buckets.SSRF`.
  - Inject:
    - URL internal aman (127.0.0.1, localhost, dll).
    - Di mode agresif:
      - Tambah dari `wordlists/ssrf_targets.txt` jika ada.
  - Heuristik:
    - Perubahan respon signifikan → flag “Possible SSRF parameter (heuristic)”.

- `CVEFingerprintContextModule`
  - Dari `Recon`:
    - Deteksi stack (WordPress, Laravel, Apache, Nginx, IIS, WAF, dll).
  - Output:
    - Hints:
      - “Check known CVEs/misconfig for tech X”.
    - Tidak mengklaim CVE spesifik eksploit-ready.
    - Membantu prioritas manual.

### 3. Modular & Extendable

- Core:
  - `ScanContext`, `FullReconWithConcurrency`, `ClassifyParams`
- ContextModules:
  - Mudah ditambah:
    - Integrasi `ffuf`
    - Integrasi `subfinder`, `httpx` lebih dalam
    - Modul template/CVEs lain

---

## Instalasi

### 1. Prasyarat

Wajib:
- Go 1.21+ (untuk build)
- Akses internet (untuk instalasi & scanning)

Direkomendasikan (untuk fullpower):
- `git`
- Koneksi yang stabil
- VPS / mesin kuat untuk `--fullpower-aggressive`

Opsional (dipakai otomatis jika ada):
- [`gau`](https://github.com/lc/gau)
- [`waybackurls`](https://github.com/tomnomnom/waybackurls)
- [`subfinder`](https://github.com/projectdiscovery/subfinder)
- [`httpx`](https://github.com/projectdiscovery/httpx)
- [`ffuf`](https://github.com/ffuf/ffuf)

### 2. Clone & Setup (disarankan)

```bash
git clone https://github.com/D0Lv-1N/autohunt.git
cd autohunt

chmod +x setup.sh
./setup.sh
```

`setup.sh` akan:
- Build binary `autohunt`.
- Menginstall ke lokasi global yang sesuai:
  - Linux/macOS: /usr/bin atau /usr/local/bin
  - Termux: $PREFIX/bin
- Mencoba install tools eksternal:
  - gau, waybackurls, subfinder, httpx, ffuf (jika Go tersedia).
- Membuat wordlists:
  - `wordlists/dirs_common.txt`
  - `wordlists/params_common.txt`
  - `wordlists/xss_payloads.txt`
  - `wordlists/ssrf_targets.txt`

Jika `setup.sh` gagal copy ke /usr/bin karena permission:
- Ikuti instruksi yang muncul (gunakan sudo atau jalankan dari direktori repo).

### 3. Build manual (opsional)

Jika tidak memakai `setup.sh`:

```bash
git clone https://github.com/D0Lv-1N/autohunt.git
cd autohunt
go build -o autohunt ./cmd/autohunt
```

- Linux/macOS/Termux:
  - `./autohunt -h`
- Windows:
  - `go build -o autohunt.exe ./cmd/autohunt`
  - `.\\autohunt.exe -h`

---

## Cara Pakai

Basic:

```bash
# Single target (domain atau URL)
autohunt -u https://target.com

# Verbose (lihat detail setiap stage & modul)
autohunt -u https://target.com -v

# Multiple targets dari file
autohunt -f targets.txt -v

# Atur timeout global (detik)
autohunt -u https://target.com -timeout 900 -v
```

Output utama:
- `autohunt_result.json`
  - Berisi array temuan dengan field:
    - `target`
    - `endpoint`
    - `module`
    - `type`
    - `severity`
    - `confidence`
    - `evidence`
    - `tags`

---

## Mode Fullpower

Secara default:
- `--fullpower` / `-F` bernilai true.

### 1. Mode Fullpower Terstruktur (`--fullpower` / `-F`)

Contoh:

```bash
autohunt -u https://target.com -F -c 20 -v
```

- Apa yang dilakukan:
  - FullRecon terstruktur:
    - Recon, crawl, URL pool, live filter, buckets.
  - Jalankan semua ContextModule:
    - SensitiveFiles, DirListing, Headers, CORS,
    - XSS, SQLi error-based, LFI, OpenRedirect, SSRF heuristics, CVE hints.
  - Concurrency dikontrol oleh `-c` (default 10 jika tidak diubah).
- Mode ini:
  - Kuat dan relatif aman untuk penggunaan regular di scope legal.

---

## Mode Fullpower Aggressive (`--fullpower-aggressive` / `-fa`)

Contoh:

```bash
# Direkomendasikan di VPS / mesin kuat
autohunt -u https://target.com -fa -v
# atau with custom concurrency:
autohunt -u https://target.com -fa -c 50 -v
```

Perilaku:

- Memaksa fullpower aktif.
- Menampilkan peringatan:
  - Resource-intensive, recommended on VPS.
- Jika `-c` tidak di-set:
  - Auto-set concurrency ke 40 (lebih agresif).
- Menggunakan FullRecon dengan:
  - Crawl lebih dalam (limit diperbesar).
  - Lebih banyak static paths (admin, backup, .git, .env, dll).
- `ScanContext.Aggressive = true`:
  - Modul akan:
    - SensitiveFiles:
      - Tambah fuzzing path dari `wordlists/dirs_common.txt` (dengan limit).
    - XSS:
      - Tambah payload dari `wordlists/xss_payloads.txt` (limit terkontrol),
      - Cek lebih banyak kombinasi param+payload.
    - SSRF:
      - Tambah target dari `wordlists/ssrf_targets.txt` (limit),
      - Lebih banyak percobaan heuristik.
    - Modul lain dapat menambah cakupan secara aman berdasarkan flag ini.

Karakter:
- Brutal dalam arti:
  - Lebih luas (lebih banyak URL & path),
  - Lebih dalam (lebih banyak payload & kombinasi),
  - Lebih cepat (concurrency tinggi).
- Tetap:
  - Non-destructive:
    - Menghindari aksi DoS,
    - Menghindari payload destructive,
    - Fokus GET/cek aman,
    - Ada batas jumlah percobaan.

Gunakan:
- HANYA untuk:
  - VPS / environment kuat,
  - Scope bug bounty yang mengizinkan scanning agresif,
  - Bukan untuk target random.

---

## Struktur Project (Ringkas)

```text
cmd/autohunt/main.go          # CLI & pipeline, -F & -fa orchestration
internal/core/types.go        # Target, Finding, Module, ContextModule
internal/core/context.go      # ScanContext (Buckets, Concurrency, Aggressive)
internal/core/recon.go        # ReconBasicWithConcurrency
internal/core/crawler.go      # CrawlBasicWithConcurrency
internal/core/fullrecon.go    # FullReconWithConcurrency, URL pool, live filter, ClassifyParams
internal/core/report.go       # SaveFindingsJSON
internal/core/targets.go      # LoadTargets & normalizeURL

internal/modules/
  senstive_file.go            # SensitiveFilesModule + SensitiveFilesContextModule (+ dirs_common in -fa)
  dir_listing.go              # DirListingModule + DirListingContextModule
  security_headers.go         # SecurityHeadersModule + ContextModule
  moodules.go                 # CORSModule + CORSContextModule
  xss_reflect.go              # XSSReflectModule + ContextModule (XSS buckets + xss_payloads in -fa)
  sqli_error.go               # SQLiErrorContextModule (bucket-based, error-based)
  lfi_basic.go                # LFIBasicModule + LFIBasicContextModule (bucket-based)
  redirect_ssrf.go            # OpenRedirectContextModule + SSRFContextModule
  cve_fingerprint.go          # CVEFingerprintContextModule (tech hints)

wordlists/
  dirs_common.txt             # Path sensitif/umum (digunakan di -fa)
  params_common.txt           # Param umum (cadangan, bisa dipakai modul lanjutan)
  xss_payloads.txt            # Payload XSS terkurasi (dipakai di -fa)
  ssrf_targets.txt            # Target SSRF aman (dipakai di SSRF heuristik, terutama -fa)
```

---

## Disclaimer

- autohunt adalah alat bantu.
- Hasil scan:
  - Adalah candidate findings dengan evidence dan confidence.
  - Tugas final:
    - Tetap di tangan hunter untuk memvalidasi dan menyusun laporan yang tepat.
- Selalu patuhi:
  - Rules of Engagement,
  - Program Policy,
  - Hukum yang berlaku.