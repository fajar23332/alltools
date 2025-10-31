
# ⚡ alltools — Fullpower Bug-Hunting Installer  

> **One Command, Full Power 🔥**  
> Installer otomatis buat semua tools bug-hunting favorit lo — tinggal jalanin `./install.sh` dan semuanya beres.  

---


🧠 Fitur Utama

⚙️ Fitur	📋 Deskripsi

🧩 Auto Detect OS	Skrip otomatis deteksi package manager (apt, dnf, pacman, termux)
⚡ Smart Install	Cek versi sebelum install, skip yang sudah terbaru
🔁 Update Otomatis	Tools lama diperbarui tanpa hapus file lama
💾 Log Lengkap	Semua aktivitas tersimpan di folder install_logs/
🧰 Modular Ready	Bisa dipisah per-modul: setup-go, setup-apt, dll
🧠 Fallback Mode	Kalau go install gagal → auto ambil release binary



---

📦 Tools yang Diinstall

subfinder, assetfinder, amass, gau, waybackurls, httpx,
naabu, dnsx, nuclei, ffuf, feroxbuster, gobuster, gospider,
httprobe, chaos-client, sqlmap, masscan, nmap, whatweb,
wpscan, eyewitness, trufflehog, subjack, sublister,
shuffledns, sensitivefinder, goth, aquatone, dalfox,
gowitness, gauplus, subfinder2


---

🧱 Struktur Folder

alltools/
 ┣ 📜 install.sh               # Master installer
 ┣ 📂 install_logs/            # Tempat semua log
 ┗ 📂 modules/ (opsional)      # Kalau mau dipisah per-modul


---
## 🚀 Quick Start  
```markdown


# 1️⃣ Clone repository
git clone https://github.com/fajar23332/alltools.git
cd alltools

# 2️⃣ Beri permission biar bisa dieksekusi
chmod +x install.sh

# 3️⃣ Jalankan installer
./install.sh

```
🧩 Cara Lihat Log
----
```
# Lihat log instalasi terbaru
ls -1 install_logs | tail -n 5

# Lihat proses real-time
tail -f install_logs/install_*.log

# Mode debug detail
bash -x ./install.sh 2>&1 | tee debug.log

```

---

🩻 Troubleshooting
---
```
❌ Masalah                                	💡 Solusi

$ Permission denied	sudo             chown -R "$USER":"$USER" ~/alltools
$ go not found                       sudo apt install -y golang
$ pipx error                         python3 -m pip install --user pipx && pipx ensurepath

```



🧰 Command Tambahan
---
```
# Ubah permission semua file .sh
find . -type f -name "*.sh" -exec chmod +x {} \;

# Jalankan hanya checker (jika tersedia)
./install.sh --check-only

```

---

💬 Kontribusi

1. Fork repo ini


2. Tambah/modifikasi installer di install.sh atau modules/


3. Tambah tool ke variabel TOOLS_TO_CHECK


4. Kirim Pull Request — biar makin fullpower 💪




---

⚖️ Lisensi

Proyek ini bebas dipakai dan dimodifikasi.
Boleh tambahin lisensi MIT / Apache sesuai kebutuhan lo.



❤️ Made with passion by Fajar23332
---
