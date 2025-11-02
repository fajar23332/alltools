# BUG-x Toolkit

Toolkit otomatis untuk instalasi, verifikasi, dan orkestrasi workflow bug hunting.

## Instalasi Cepat

```bash
git clone https://github.com/D0Lv-1N/BUGx.git
cd ~/BUGx
python3 setup.py
```

`setup.py` akan:

- Menjalankan update paket (`apt`/`pkg`) sesuai platform.
- Membuat venv global di `~/venv`, memasang `requirements.txt`, dan menambahkan alias `venv` / `venvoff` ke shell.
- Menginstal daftar tool bug hunting (disesuaikan untuk Linux / Termux / macOS).
- Mengunduh wordlist penting ke `~/BUGx/wordlists/`.
- Menjalankan `report.py` untuk memverifikasi setiap tool dan menyegarkan `help_output/*.json`.

> **Catatan:** Setelah instalasi pertama, jalankan `source ~/.bashrc` agar alias `venv` tersedia pada sesi shell berikutnya.

## Menjalankan Orkestrasi CLI

```bash
python3 tools.py
```

- Jika dijalankan di luar venv, skrip otomatis memanggil kembali dirinya menggunakan `~/venv/bin/python3`.
- Header ASCII “BUG-x” akan muncul di setiap tampilan.
- Pilih bahasa & mode (single tool atau kombinasi pipeline).
- Untuk setiap tool, pengguna akan mendapat contoh input URL / path yang benar dan pilihan flag standar atau custom (berdasarkan `help_output/<tool>.json`).
- Hasil single tool disimpan di `~/BUGx/singletarget/<target_singkat>/`, sedangkan mode kombinasi ke `~/BUGx/Kombinasitools/<target_singkat>/`.
- Setelah ringkasan, antarmuka otomatis kembali ke menu utama. Keluar menampilkan pesan motivasi `SEMANGAT KAWAN`.

## Struktur Folder

```
~/BUGx/
├── help_output/        # hasil probe masing-masing tool (JSON)
├── wordlists/          # directories.txt, apis.txt, params.txt, dst
├── install_report.json # laporan instalasi setup.py
├── help_report.json    # laporan probe report.py
├── setup.py            # installer utama
├── report.py           # verifikasi tool dan wordlist
├── tools.py            # CLI orkestrator
└── README.md
```

Selamat berburu bug! 🕵️‍♂️
