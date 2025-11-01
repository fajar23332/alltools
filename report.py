#!/usr/bin/env python3
# report_json.py
# Versi: perbaikan (JSON-centric)
# Tujuan: probe tiap tool dengan mencoba flag help; simpan per-tool JSON; hasil ringkasan ke install_report.json
# Penjelasan (bahasa Indonesia): setiap fungsi diberi komentar singkat.
# Author: D0Lv.1N • Built by GPT-5 (keterangan kecil)
# Requirements (opsional): Python 3.8+, tidak perlu paket eksternal.

import os
import shutil
import json
import subprocess
from pathlib import Path
from datetime import datetime

# -------------------------
# Konfigurasi
# -------------------------
ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "help_report.json"
HELP_DIR = Path.home() / "alltools" / "help_output"
WORDLIST_DIR = Path.home() / "alltools" / "wordlists"
CMD_TIMEOUT = 8  # detik timeout tiap panggilan -h
# urutan flag untuk dicoba — mulai dari yang paling umum
TRY_FLAGS = ["-h", "--help", "--version", "-v", "help"]

# Daftar tool default (sinkronkan dengan setup.py jika perlu)
TOOLS = [
    "subfinder","assetfinder","amass","gau","waybackurls","httpx",
    "naabu","dnsx","nuclei","ffuf","feroxbuster","gobuster","gospider",
    "httprobe","sqlmap","masscan","nmap","whatweb","wpscan",
    "eyewitness","subjack","sublister","shuffledns",
    "dalfox","gowitness","XSpear","xpoc","paramspider"
]

# -------------------------
# Helper: aktifkan venv (non-interactive)
# -------------------------
def maybe_activate_venv():
    """
    Jika ~/venv/bin ada, tambahkan ke PATH process ini.
    Ini efektif 'mengaktifkan' venv untuk subprocess yang dijalankan dari script ini.
    """
    venv_bin = Path.home() / "venv" / "bin"
    if venv_bin.exists() and venv_bin.is_dir():
        # prepend ke PATH supaya binary/pip di venv prioritas
        p = str(venv_bin)
        os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
        return True, p
    return False, None

# -------------------------
# Helper: jalankan help cmd
# Kita coba dua bentuk: arg-list (lebih aman) lalu shell fallback
# -------------------------
def run_help_cmd(cmd_path, flag):
    """
    Coba jalankan [cmd_path, flag] lalu fallback ke shell string jika perlu.
    Kembalikan tuple (rc, combined_output).
    """
    try:
        p = subprocess.run([cmd_path, flag], capture_output=True, text=True, timeout=CMD_TIMEOUT)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except Exception:
        # fallback: coba sebagai shell string (beberapa wrapper butuh ini)
        try:
            cmdstr = f"'{cmd_path}' {flag}"
            p2 = subprocess.run(cmdstr, shell=True, capture_output=True, text=True, timeout=CMD_TIMEOUT)
            out2 = (p2.stdout or "") + (p2.stderr or "")
            return p2.returncode, out2
        except Exception as e:
            return 999, f"EXC: {e}"

# -------------------------
# Probe satu tool
# -------------------------
def probe_tool(tool):
    """
    1) Temukan path via shutil.which (cari juga Capitalized tool sebagai fallback)
    2) Jika tidak ada -> status "missing"
    3) Jika ada -> coba TRY_FLAGS satu per satu; jika ada output non-empty -> anggap OK
    4) Simpan file JSON di HELP_DIR/<tool>.json berisi info & raw_output (dipotong jika besar)
    """
    path = shutil.which(tool) or shutil.which(tool.capitalize())
    HELP_DIR.mkdir(parents=True, exist_ok=True)

    out_file = HELP_DIR / f"{tool}.json"

    if not path:
        # tulis JSON kecil supaya tools.py bisa baca nanti
        data = {
            "tool": tool,
            "status": "missing",
            "path": None,
            "checked_at": datetime.now().isoformat()
        }
        out_file.write_text(json.dumps(data, indent=2))
        return "missing", None, data

    # ditemukan path -> coba flags
    combined_log = ""
    for flag in TRY_FLAGS:
        rc, out = run_help_cmd(path, flag)
        combined_log += f"\n--- tried: {flag} (rc={rc}) ---\n"
        combined_log += out if out else ""
        # treat as OK jika ada output non-blank
        if out and out.strip():
            # sedikit parse: ambil baris yang kelihatan seperti "flag — desc" (garis yg mengandung '-' awal)
            flags_parsed = []
            for line in out.splitlines():
                s = line.strip()
                # masukin baris yang mulai dengan '-' atau '--' atau '/-'
                if s.startswith("-") or s.startswith("--") or s.startswith("/"):
                    parts = s.split(None, 1)
                    flagname = parts[0]
                    desc = parts[1].strip() if len(parts) > 1 else ""
                    flags_parsed.append({"flag": flagname, "desc": desc})
            # trunc raw output untuk simpan (jangan melebihi 50k)
            raw_trunc = out if len(out) <= 50000 else out[:50000] + "\n...[truncated]..."
            data = {
                "tool": tool,
                "status": "ok",
                "path": path,
                "detected_flag": flag,
                "parsed_flags": flags_parsed,
                "raw_output": raw_trunc,
                "checked_at": datetime.now().isoformat()
            }
            out_file.write_text(json.dumps(data, indent=2))
            return "ok", path, data

    # jika sampai sini -> path ada tapi gaada help-like output -> anggap "no_help" (treatment: missing)
    data = {
        "tool": tool,
        "status": "no_help",
        "path": path,
        "note": "binary present but no help output from tried flags",
        "raw_probe_log": combined_log[:50000],
        "checked_at": datetime.now().isoformat()
    }
    out_file.write_text(json.dumps(data, indent=2))
    # treat as missing for higher-level logic
    return "no_help", path, data

# -------------------------
# GF dan Wordlist checks
# -------------------------
def check_gf():
    """
    Jika gf ada, ambil gf -h (ringkas) dan gf -list (templates)
    Kembalikan dict {gf_path, gf_tools_summary, templates_list}
    """
    gf_path = shutil.which("gf")
    if not gf_path:
        return {"gf_path": None, "gf_tools": None, "templates": []}
    # gf -h
    try:
        p = subprocess.run([gf_path, "-h"], capture_output=True, text=True, timeout=5)
        gf_tools = (p.stdout or p.stderr or "").strip()
    except Exception:
        gf_tools = "[error reading gf -h]"
    # gf -list
    try:
        q = subprocess.run([gf_path, "-list"], capture_output=True, text=True, timeout=5)
        templates = [x.strip() for x in (q.stdout or "").splitlines() if x.strip()]
    except Exception:
        templates = []
    return {"gf_path": gf_path, "gf_tools": gf_tools, "templates": templates}

def check_wordlists():
    """
    Kembalikan daftar path file di ~/alltools/wordlists jika ada
    """
    if not WORDLIST_DIR.exists():
        return []
    return [str(p) for p in sorted(WORDLIST_DIR.glob("*")) if p.is_file()]

# -------------------------
# Main flow
# -------------------------
def main():
    # step 0: maybe activate venv by prepending PATH
    venv_on, venv_bin = maybe_activate_venv()
    if venv_on:
        print(f"[*] venv ditemukan dan akan diprioritaskan (path added): {venv_bin}")
    else:
        print("[*] venv tidak ditemukan di ~/venv — akan lanjut tanpa venv (tools Python mungkin tidak terdeteksi)")

    # step 1: probe semua tools
    installed = []
    missing = []
    details = {}

    print("[*] Memproses tools list ... (ini bisa butuh beberapa detik per tool)")

    for t in TOOLS:
        print(f"  -> mengecek {t} ...", end="", flush=True)
        try:
            status, path, info = probe_tool(t)
            details[t] = info
            if status == "ok":
                installed.append(t)
                print(" OK")
            else:
                missing.append(t)
                print(f" MISSING/NOHELP ({status})")
        except Exception as e:
            # jangan biarkan crash; catat dan teruskan
            details[t] = {"tool": t, "status": "error", "error": str(e)}
            missing.append(t)
            print(" ERROR (cek details)")

    # step 2: gf & wordlists
    gf_data = check_gf()
    wlists = check_wordlists()

    # step 3: simpan ringkasan JSON (sinkron dengan setup.py keys)
    summary = {
        "installed": sorted(installed),
        "missing": sorted([m for m in set(missing) if m not in installed]),
        "details": details,
        "gf_data": gf_data,
        "wordlists": wlists,
        "timestamp": datetime.now().isoformat()
    }

    REPORT_PATH.write_text(json.dumps(summary, indent=2))
    print(f"[*] Laporan disimpan -> {REPORT_PATH}")

    # tampilan singkat ke terminal
    print("\n=== Ringkasan singkat ===")
    print("Installed:", len(installed), "tools")
    print("Missing/no-help:", len(summary["missing"]))
    print("GF templates:", len(gf_data.get("templates") or []))
    print("Wordlists:", len(wlists))
    print("Wanna inspect the full JSON? ->", REPORT_PATH)

if __name__ == "__main__":
    main()
