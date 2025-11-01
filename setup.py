#!/usr/bin/env python3
"""
setup.py
- Idempotent installer for a curated set of CLI tools used for bug-hunting.
- Usage:
    - Check only:      python3 setup.py --check
    - Install missing: sudo python3 setup.py
Notes:
- Best-effort for Debian/Ubuntu. Some installs require `go`, `pipx`, `gem`, or `apt`.
- Script prints actions and writes a short JSON summary to install_report.json
"""
import os, sys, shutil, json, subprocess, platform, argparse, tempfile
from pathlib import Path






ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "install_report.json"

# === TOOL LIST & preferred install method ===
TOOLS = {
    "subfinder":       ("go", "github.com/projectdiscovery/subfinder/v2/cmd/subfinder"),
    "assetfinder":     ("go", "github.com/tomnomnom/assetfinder"),
    "amass":           ("snap", "amass"),
    "gau":             ("go", "github.com/lc/gau/v2/cmd/gau"),
    "waybackurls":     ("go", "github.com/tomnomnom/waybackurls"),
    "httpx":           ("go", "github.com/projectdiscovery/httpx/cmd/httpx"),
    "naabu":           ("go", "github.com/projectdiscovery/naabu/v2/cmd/naabu"),
    "dnsx":            ("go", "github.com/projectdiscovery/dnsx/cmd/dnsx"),
    "nuclei":          ("go", "github.com/projectdiscovery/nuclei/v3/cmd/nuclei"),
    "ffuf":            ("go", "github.com/ffuf/ffuf"),
    "feroxbuster":     ("snap", "feroxbuster"),
    "gobuster":        ("apt", "gobuster"),
    "gospider":        ("go", "github.com/jaeles-project/gospider"),
    "httprobe":        ("go", "github.com/tomnomnom/httprobe"),
    "sqlmap":          ("apt", "sqlmap"),
    "masscan":         ("apt", "masscan"),
    "nmap":            ("apt", "nmap"),
    "whatweb":         ("apt", "whatweb"),
    "wpscan":          ("gem", "wpscan"),
    "subjack":         ("go", "github.com/haccer/subjack"),
    "shuffledns":      ("go", "github.com/projectdiscovery/shuffledns/cmd/shuffledns"),
    "dalfox":          ("go", "github.com/hahwul/dalfox/v2"),
    "gowitness":       ("go", "github.com/sensepost/gowitness"),
    "XSpear":          ("gem", "XSpear"),
    "gf": ("go", "github.com/tomnomnom/gf"),
    "xpoc":            ("xpoc_release", "chaitin/xpoc"),  # custom installer below
    #venv
    "sublister":       ("git-python-venv", "https://github.com/aboul3la/Sublist3r.git"),
    "eyewitness":      ("git-python-venv", "https://github.com/RedSiege/EyeWitness.git"),
    "paramspider": ("git-python-venv", "https://github.com/devanshbatham/paramspider"),
}

# === Helpers ===
def sh(cmd, check=False, capture=False, env=None):
    print(f"> {cmd}")
    return subprocess.run(cmd, shell=True, check=check, capture_output=capture, text=True, env=env)

def is_installed(binname):
    return shutil.which(binname) is not None

def go_installed():
    return shutil.which("go") is not None

def ensure_go():
    if go_installed():
        return True
    print("[!] go not found — attempting apt install golang-go (requires sudo)")
    sh("apt-get update -y && apt-get install -y golang-go", check=True)
    return go_installed()

def ensure_pipx():
    if shutil.which("pipx"):
        return True
    print("[*] pipx not found — installing python3-pip and pipx (user)")
    sh("apt-get update -y && apt-get install -y python3-pip python3-venv", check=True)
    sh("python3 -m pip install --user pipx", check=True)
    sh("python3 -m pipx ensurepath", check=False)
    os.system("export PATH=$HOME/.local/bin:$PATH")
    user_base = sh("python3 -m site --user-base", capture=True)
    if user_base.returncode == 0:
        ub = user_base.stdout.strip()
        binpath = Path(ub) / "bin"
        os.environ["PATH"] = f"{binpath}:{os.environ.get('PATH','')}"
    return shutil.which("pipx") is not None

def ensure_gem():
    if shutil.which("gem"):
        return True
    print("[*] gem not found — installing ruby-full")
    sh("apt-get update -y && apt-get install -y ruby-full build-essential", check=True)
    return shutil.which("gem") is not None

def gopath_bin_dir():
    gobin = os.environ.get("GOBIN")
    if gobin:
        return Path(gobin)
    p = subprocess.run("go env GOPATH", shell=True, capture_output=True)
    if p.returncode == 0:
        gp = p.stdout.decode().strip()
        if gp:
            return Path(gp) / "bin"
    return Path.home() / "go" / "bin"

def move_to_usr_local(binpath: Path, name: str):
    dest = Path("/usr/local/bin") / name
    try:
        print(f"-> moving {binpath} -> {dest} (requires sudo)")
        sh(f"sudo mv -f '{binpath}' '{dest}'", check=True)
        sh(f"sudo chmod +x '{dest}'", check=True)
        return True
    except Exception as e:
        print("! mv failed:", e)
        return False


# ---------------------------
# paste ke setup.py (helpers area)
# ---------------------------
from pathlib import Path
import shutil

def install_wordlists():
    """
    Idempotent: buat ~/alltools/wordlists dan download beberapa file penting dari SecLists.
    Jika raw URLs 404, fallback: git clone SecLists ke /tmp dan copy file.
    """
    WL_DIR = Path.home() / "alltools" / "wordlists"
    WL_DIR.mkdir(parents=True, exist_ok=True)
    print("\n📂 [*] Preparing wordlists directory:", WL_DIR)

    # preferensi file + beberapa fallback URL/patokan
    files = {
        "common.txt": [
            "https://raw.githubusercontent.com/danielmiessler/SecLists/main/Discovery/Web-Content/common.txt",
            "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/common.txt"
        ],
        "directory-list-2.3-medium.txt": [
            "https://raw.githubusercontent.com/danielmiessler/SecLists/main/Discovery/Web-Content/directory-list-2.3-medium.txt",
            # fallback: popular gist if not in SecLists
            "https://gist.githubusercontent.com/diananerd/9eb14515bacd2655c49a17742ef9a135/raw/directory-list-2.3-medium.txt"
        ],
        "raft-large-words.txt": [
            "https://raw.githubusercontent.com/danielmiessler/SecLists/main/Discovery/Web-Content/raft-large-words.txt",
            "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/raft-large-words.txt"
        ],
        # parameters list fallback -> use burp-parameter-names (exists)
        "params.txt": [
            "https://raw.githubusercontent.com/danielmiessler/SecLists/main/Discovery/Web-Content/burp-parameter-names.txt",
            "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Discovery/Web-Content/burp-parameter-names.txt"
        ]
    }

    # try direct download first (try each candidate URL), else fallback to cloning repo
    need_clone = []
    for name, url_list in files.items():
        dest = WL_DIR / name
        if dest.exists():
            print(f"[+] wordlist exists -> {dest} (skip)")
            continue

        success = False
        for url in url_list:
            print(f"[+] Trying {url} -> {dest}")
            try:
                sh(f"curl -fsSL -o '{dest}' '{url}'", check=True)
                success = True
                break
            except Exception as e:
                # continue to next candidate url
                # keep going — not fatal yet
                pass

        if not success:
            print(f"[!] Direct download failed for {name}, will try cloning SecLists later")
            need_clone.append(name)

    # if any failed, do single git clone and copy missing files
    if need_clone:
        TMP = Path(tempfile.mkdtemp(prefix="seclists-"))
        try:
            repo = "https://github.com/danielmiessler/SecLists.git"
            print(f"[+] Cloning SecLists -> {TMP} (to recover {len(need_clone)} file(s))")
            sh(f"git clone --depth 1 {repo} '{TMP}'", check=True)
            for name in need_clone:
                # try a few likely paths
                candidates = [
                    TMP / "Discovery" / "Web-Content" / name,
                    TMP / "Discovery" / "Parameters" / name,
                    TMP / "Discovery" / "Web-Content" / name.replace("params", "burp-parameter-names.txt")
                ]
                found = False
                for c in candidates:
                    if c.exists():
                        shutil.copy2(c, WL_DIR / name)
                        print(f"[OK] Copied {c} -> {WL_DIR/name}")
                        found = True
                        break
                if not found:
                    print(f"[WARN] {name} not found in cloned SecLists; skipping")
        except Exception as e:
            print("! Failed to clone SecLists or copy files:", e)
        finally:
            try:
                shutil.rmtree(TMP, ignore_errors=True)
            except Exception:
                pass

    print("[OK] wordlists ready at", WL_DIR)
    return True
def install_gf_and_patterns():
    """
    Install gf globally (via go) and clone/update Gf patterns to ~/.gf
    """
    GF_IMPORT = "github.com/tomnomnom/gf"
    GF_BIN = "gf"

    print("\n--- Installing gf ---")
    installed = False
    try:
        # pakai helper kalau ada
        if 'install_go_tool' in globals():
            installed = install_go_tool(GF_IMPORT, GF_BIN)
        else:
            # fallback manual go install
            if not go_installed():
                ensure_go()
            sh(f"GO111MODULE=on go install {GF_IMPORT}@latest", check=True)
            bin_candidate = gopath_bin_dir() / GF_BIN
            if bin_candidate.exists():
                move_to_usr_local(bin_candidate, GF_BIN)
                installed = True
            else:
                # fallback tambahan buat sistem tertentu (UserLand/Termux)
                alt_path = Path.home() / "go" / "bin" / GF_BIN
                if alt_path.exists():
                    move_to_usr_local(alt_path, GF_BIN)
                    installed = True
    except Exception as e:
        print("! gf install failed:", e)

    # ✅ verifikasi final
    if installed or shutil.which("gf"):
        gf_path = shutil.which("gf")
        print(f"[OK] gf available globally -> {gf_path}")
    else:
        print("[WARN] gf not installed globally; continuing anyway")

    # ============================================================
    # CLONE / UPDATE PATTERNS
    # ============================================================
    GF_DIR = Path.home() / ".gf"
    repo = "https://github.com/1ndianl33t/Gf-Patterns.git"

    if GF_DIR.exists():
        print("[*] Updating existing ~/.gf patterns...")
        try:
            sh(f"cd '{GF_DIR}' && git pull --ff-only", check=False)
        except Exception as e:
            print("[!] git pull failed, skipping update:", e)
    else:
        print("[+] Cloning Gf-Patterns -> ~/.gf")
        try:
            sh(f"git clone --depth 1 {repo} '{GF_DIR}'", check=True)
        except Exception as e:
            print("! clone GF patterns failed:", e)

    if GF_DIR.exists():
        print("[OK] GF patterns ready at", GF_DIR)

    # ============================================================
    # OPTIONAL: Auto-enable bash completion
    # ============================================================
    completion_path = Path.home() / "go" / "src" / "github.com" / "tomnomnom" / "gf" / "gf-completion.bash"
    bashrc = Path.home() / ".bashrc"
    if completion_path.exists():
        line = f"source {completion_path}"
        if bashrc.exists() and line not in bashrc.read_text():
            with open(bashrc, "a") as f:
                f.write(f"\n# gf auto-completion\n{line}\n")
            print("[+] Added gf auto-completion to ~/.bashrc")

    print("[OK] gf installation and pattern setup complete ✅")
    return True
# Example: call these from main() before final report/save
# install_wordlists()
# install_gf_and_patterns()

# minimal github release fetch helper (tries to pick linux asset)
def download_github_release(owner_repo, dest):
    api = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    try:
        out = subprocess.run(
            f"curl -s {api} | grep browser_download_url | grep linux | head -n1 | cut -d '\"' -f4",
            shell=True, capture_output=True)
        url = out.stdout.decode().strip()
        if not url:
            return False
        print("-> downloading", url)
        sh(f"curl -L -s -o '{dest}' '{url}'", check=True)
        return True
    except Exception as e:
        print("! github release download failed:", e)
    return False


# === Installers per method ===
def install_go_tool(import_path, binname):
    if not ensure_go():
        print("! go not available; skipping go install for", binname)
        return False
    try:
        print(f"[+] Installing {binname} via 'go install {import_path}@latest' ...")
        sh(f"GO111MODULE=on go install {import_path}@latest", check=True)
        bin_candidate = gopath_bin_dir() / binname
        if bin_candidate.exists():
            return move_to_usr_local(bin_candidate, binname)
        for p in [Path("/usr/local/go/bin"), Path.home() / "go" / "bin"]:
            if (p / binname).exists():
                return move_to_usr_local(p / binname, binname)
    except subprocess.CalledProcessError as e:
        print("! go install failed:", e)
    return False

def install_apt(pkgname, binname=None):
    try:
        print(f"[+] apt install {pkgname}")
        sh(f"apt-get update -y && apt-get install -y {pkgname}", check=True)
        return is_installed(binname or pkgname)
    except Exception as e:
        print("! apt install failed:", e)
        return False

def install_gem(gemname, binname):
    if not ensure_gem():
        return False
    try:
        print(f"[+] gem install {gemname}")
        if os.geteuid() == 0:
            sh(f"gem install {gemname} --no-document", check=True)
        else:
            # user-install, then link
            sh(f"gem install --user-install {gemname} --no-document", check=True)
            out = subprocess.run("ruby -e 'print Gem.user_dir'", shell=True, capture_output=True)
            gem_bin = Path(out.stdout.decode().strip()) / "bin"
            if gem_bin.exists():
                # add to PATH for current session
                os.environ["PATH"] = f"{gem_bin}:{os.environ.get('PATH','')}"
                try:
                    sh(f"sudo ln -sf '{gem_bin}/{binname}' /usr/local/bin/{binname}", check=False)
                except Exception:
                    pass
        out = subprocess.run("ruby -e 'print Gem.bindir'", shell=True, capture_output=True)
        if out.returncode == 0:
            gembindir = out.stdout.decode().strip()
            cand = Path(gembindir) / binname
            if cand.exists():
                return move_to_usr_local(cand, binname)
    except Exception as e:
        print("! gem install failed:", e)
    return False
#venv
def ensure_global_venv():
    venv_dir = Path.home() / "venv"
    if not venv_dir.exists():
        print("[*] Creating global venv at ~/venv ...")
        sh(f"python3 -m venv '{venv_dir}'", check=True)
    print("[OK] Global venv ready ->", venv_dir)
    return venv_dir

#eyewtiness
def install_eyewitness():
    print("\n--- Installing EyeWitness ---")
    repo = "https://github.com/RedSiege/EyeWitness.git"
    dest = Path.home() / "EyeWitness"
    tmp = Path(tempfile.mkdtemp(prefix="eyewitness-"))
    try:
        sh(f"git clone --depth 1 {repo} '{tmp}'", check=True)
        sh(f"mv -f '{tmp}' '{dest}'", check=True)

        venv = Path.home() / "venv"
        setup_dir = dest / "setup"
        if setup_dir.exists():
            print("[*] Running setup script (creates venv)...")
            sh(f"cd '{setup_dir}' && sudo ./setup.sh", check=True)
        else:
            print("[WARN] setup/ dir not found, skipping auto-setup")

        # create wrapper
        wrapper_path = "/usr/local/bin/eyewitness"
        wrapper = f"""#!/usr/bin/env bash
S_DIR="{dest}"
if [ -x "$S_DIR/eyewitness-venv/bin/python" ]; then
  exec "$S_DIR/eyewitness-venv/bin/python" "$S_DIR/Python/EyeWitness.py" "$@"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 "$S_DIR/Python/EyeWitness.py" "$@"
else
  echo "[!] Virtual env not found, reinstall EyeWitness or run manually:"
  echo "cd $S_DIR && source eyewitness-venv/bin/activate && python Python/EyeWitness.py"
  exit 1
fi
"""
        Path("/tmp/eyewitness_wrap.sh").write_text(wrapper)
        sh(f"sudo mv /tmp/eyewitness_wrap.sh {wrapper_path}", check=True)
        sh(f"sudo chmod +x {wrapper_path}", check=True)
        print("[OK] EyeWitness installed successfully — run 'eyewitness --help'")
        return True
    except Exception as e:
        print("! EyeWitness install failed:", e)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# === Sublist3r Installer (fixed version) ===
def install_sublist3r():
    print("\n--- Installing Sublist3r ---")
    repo = "https://github.com/aboul3la/Sublist3r.git"
    dest = Path.home() / "Sublist3r"
    tmp = Path(tempfile.mkdtemp(prefix="sublist3r-"))

    try:
        # Clone atau update repo
        if dest.exists():
            print("[*] Updating existing Sublist3r repo...")
            sh(f"cd '{dest}' && git pull --ff-only", check=False)
        else:
            print(f"[+] Cloning {repo} -> {dest}")
            sh(f"git clone --depth 1 {repo} '{tmp}'", check=True)
            sh(f"mv -f '{tmp}' '{dest}'", check=True)

        # Gunakan venv di dalam repo (bukan global)
        venv = dest / ".venv"
        if not venv.exists():
            print("[*] Creating Python venv for Sublist3r...")
            sh(f"python3 -m venv '{venv}'", check=True)
        else:
            print("[*] Using existing venv ->", venv)

        # Upgrade pip dan install requirements.txt + modul tambahan
        sh(f"'{venv}/bin/pip' install --upgrade pip setuptools wheel", check=False)
        req = dest / "requirements.txt"
        if req.exists():
            print("[*] Installing Sublist3r requirements...")
            sh(f"'{venv}/bin/pip' install -r '{req}'", check=False)
        else:
            print("[!] requirements.txt not found, installing essentials manually...")
        # Tambahan penting biar gak error "No module named 'dns'"
        sh(f"'{venv}/bin/pip' install dnspython requests colorama", check=False)

        # Buat wrapper global /usr/local/bin/sublister
        wrapper_path = "/usr/local/bin/sublister"
        wrapper = f"""#!/usr/bin/env bash
S_DIR="{dest}"
PY="$S_DIR/.venv/bin/python"
if [ -x "$PY" ]; then
  exec "$PY" "$S_DIR/sublist3r.py" "$@"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 "$S_DIR/sublist3r.py" "$@"
else
  echo "[!] Virtual env not found, reinstall Sublist3r or run manually:"
  echo "cd $S_DIR && source .venv/bin/activate && python sublist3r.py"
  exit 1
fi
"""
        Path("/tmp/sublister_wrap.sh").write_text(wrapper)
        sh(f"sudo mv /tmp/sublister_wrap.sh {wrapper_path}", check=True)
        sh(f"sudo chmod +x {wrapper_path}", check=True)

        print("[OK] Sublist3r installed successfully — run 'sublister -h'")
        return True

    except Exception as e:
        print("! Sublist3r install failed:", e)
        return False

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
#paramspider
def install_paramspider(git_url):
    dest = Path.home() / "paramspider"
    if dest.exists():
        print("[*] Updating paramspider...")
        sh(f"cd '{dest}' && git pull", check=False)
    else:
        print(f"[+] Cloning {git_url} -> {dest}")
        sh(f"git clone --depth 1 {git_url} '{dest}'", check=True)

    venv = Path.home() / "venv"
    if not venv.exists():
        print("[*] Creating venv for paramspider...")
        sh(f"python3 -m venv '{venv}'", check=True)

    print("[*] Installing requirements inside venv...")
    sh(f"'{venv}/bin/pip' install -U pip wheel", check=True)
    sh(f"cd '{dest}' && '{venv}/bin/pip' install .", check=True)

    # buat wrapper biar bisa dipanggil langsung
    wrapper = "/usr/local/bin/paramspider"
    script = f"""#!/usr/bin/env bash
cd "{dest}"
source "{venv}/bin/activate"
exec python3 -m paramspider "$@"
"""
    Path("/tmp/paramspider.sh").write_text(script)
    sh(f"sudo mv /tmp/paramspider.sh {wrapper}", check=False)
    sh(f"sudo chmod +x {wrapper}", check=False)

    return is_installed("paramspider")


# === xpoc (Xray 2.0) specific installer ===
def install_xpoc():
    print("\n--- xpoc (Xray 2.0 series)")

    # Auto-detect arch
    arch = platform.machine().lower()
    if "x86_64" in arch or "amd64" in arch:
        arch_tag = "amd64"
    elif "aarch64" in arch or "arm64" in arch:
        arch_tag = "arm64"
    else:
        arch_tag = "amd64"

    version = "0.1.0"
    url = f"https://github.com/chaitin/xpoc/releases/download/{version}/xpoc_linux_{arch_tag}.zip"

    # Auto-skip if already installed
    if Path("/usr/local/bin/xpoc").exists() or Path("/opt/xpoc/xpoc").exists():
        print("[OK] xpoc already installed — skipping download.")
        return True

    tmpd = Path(tempfile.mkdtemp(prefix="xpoc-"))
    zipf = tmpd / "xpoc.zip"
    try:
        print(f"[+] Downloading xpoc {version} for {arch_tag}")
        sh(f"curl -fsSL -o '{zipf}' '{url}'", check=True)
        print("[*] Extracting...")
        sh(f"unzip -oq '{zipf}' -d '{tmpd}'", check=True)

        # cari binary xpoc
        bin_candidate = None
        for c in tmpd.glob("xpoc*"):
            if c.is_file():
                bin_candidate = c
                break
        if not bin_candidate:
            print("! Could not find xpoc binary in archive")
            return False

        # move ke /opt/xpoc
        sh("sudo mkdir -p /opt/xpoc", check=True)
        sh(f"sudo mv -f '{bin_candidate}' /opt/xpoc/xpoc", check=True)
        sh("sudo chmod +x /opt/xpoc/xpoc", check=True)

        # wrapper global
        wrapper = "/usr/local/bin/xpoc"
        wrapper_sh = "#!/usr/bin/env bash\ncd /opt/xpoc && exec ./xpoc \"$@\"\n"
        sh(f"echo '{wrapper_sh}' | sudo tee {wrapper} >/dev/null", check=True)
        sh(f"sudo chmod +x {wrapper}", check=True)

        print("[OK] xpoc installed successfully — run 'xpoc --help'")
        return True

    except Exception as e:
        print("! xpoc install failed:", e)
        return False

    finally:
        try:
            if tmpd.exists():
                shutil.rmtree(tmpd, ignore_errors=True)
        except Exception:
            pass

# === Main logic ===
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Only check and report; no install")
    args = ap.parse_args() 
    install_wordlists()
    install_gf_and_patterns()

    installed = []
    missing = []
    details = {}

    # daftar tools yang pakai venv global
    venv_tools = ["eyewitness", "sublister", "paramspider"]
    normal_tools = [n for n in TOOLS.keys() if n not in venv_tools]

    # ============================================================
    # STEP 1 — Install semua tools biasa (tanpa venv)
    # ============================================================
    for name in normal_tools:
        method, hint = TOOLS[name]
        print("\n---", name)
        if is_installed(name):
            print(f"[OK] {name} already in PATH -> {shutil.which(name)}")
            installed.append(name)
            details[name] = {"status": "ok", "path": shutil.which(name)}
            continue
        if args.check:
            print(f"[MISS] {name} not found (check-only mode)")
            missing.append(name)
            details[name] = {"status": "missing"}
            continue

        ok = False
        if method == "go":
            ok = install_go_tool(hint, name)
        elif method == "apt":
            ok = install_apt(hint, name)
        elif method == "gem":
            ok = install_gem(hint, name)
        elif method == "snap":
            try:
                print("[*] Installing via snap (requires snapd)")
                sh("snap install " + hint, check=True)
                ok = is_installed(name)
            except Exception:
                ok = False
        elif method == "github_release":
            tmpf = f"/tmp/{name}.zip"
            ok = download_github_release(hint, tmpf)
        elif method == "xpoc_release":
            ok = install_xpoc()
        else:
            print("! Unknown install method for", name)

        if ok:
            print(f"[INSTALLED] {name}")
            installed.append(name)
            details[name] = {"status": "installed"}
        else:
            print(f"[FAILED] {name}")
            missing.append(name)
            details[name] = {"status": "failed"}

    # ============================================================
    # STEP 2 — Aktifkan global venv (~/venv)
    # ============================================================
    print("\n=== Activating global venv for Python-based tools ===")
    venv_dir = ensure_global_venv()
    sh(f"source '{venv_dir}/bin/activate'", check=False)

    # ============================================================
    # STEP 3 — Install semua tools Python yang pakai venv
    # ============================================================
    for name in venv_tools:
        print("\n---", name)
        method, hint = TOOLS[name]
        ok = False

        if name == "eyewitness":
            ok = install_eyewitness()
        elif name == "sublister":
            ok = install_sublist3r()
        elif name == "paramspider":
            ok = install_paramspider(hint)

        if ok:
            print(f"[INSTALLED] {name}")
            installed.append(name)
            details[name] = {"status": "installed"}
        else:
            print(f"[FAILED] {name}")
            missing.append(name)
            details[name] = {"status": "failed"}

    # ============================================================
    # STEP 4 — Deactivate venv dan cek xpoc terakhir
    # ============================================================
    print("\n[*] Deactivating global venv...")
    sh("deactivate", check=False)

    print("\n=== Checking xpoc (Xray 2.0 series) ===")
    if not is_installed("xpoc"):
        install_xpoc()
    else:
        print("[OK] xpoc already installed.")
# ============================================================
    # STEP 4.5 — Install gf + wordlists (opsional tapi disarankan)
    # ============================================================
    print("\n=== Installing gf + wordlists ===")
    install_wordlists()
    install_gf_and_patterns()

   # ============================================================
    # STEP 5 — Save report hasil install
    # ============================================================

    summary = {"installed": installed, "missing": missing, "details": details}

    # --- Tambahan: sertakan gf + templates + wordlists ---
    import subprocess
    from pathlib import Path

    gf_path = shutil.which("gf")
    if gf_path:
        if "gf" not in installed:
            installed.append("gf")
        details["gf"] = {"status": "ok", "path": gf_path}
    else:
        details.setdefault("gf", {"status": "missing"})

    gf_templates = []
    if gf_path:
        try:
            p = subprocess.run(["gf", "-list"], capture_output=True, text=True, timeout=5)
            gf_templates = [s.strip() for s in p.stdout.splitlines() if s.strip()]
        except Exception:
            gf_templates = []

    WL_DIR = Path.home() / "alltools" / "wordlists"
    wordlists = [str(p) for p in WL_DIR.glob("*") if p.is_file()]

    summary["gf_templates"] = gf_templates
    summary["wordlists"] = wordlists

    # --- Simpan hasil ke JSON ---
    REPORT_PATH.write_text(json.dumps(summary, indent=2))
    print("\n=== Done ===")
    print(f"Installed: {len(installed)}  Missing/Failed: {len(missing)}")
    print("Report saved to", REPORT_PATH)
    return 0

if __name__ == "__main__":
    sys.exit(main())

    
