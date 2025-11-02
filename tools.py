#!/usr/bin/env python3
"""
BUG-x CLI Orchestrator
- Menyediakan antarmuka interaktif untuk menjalankan tool single maupun workflow kombinasi.
- Menangani aktivasi venv otomatis, validasi input, pemilihan flag standar/custom, dan ringkasan hasil.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from shutil import get_terminal_size
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

# tipe union untuk command shell/list
CommandType = Union[List[str], Tuple[str, ...], str]

try:
    from pyfiglet import Figlet
except ImportError:  # pragma: no cover - fallback jika dependency belum terpasang
    print("pyfiglet belum terpasang. Jalankan 'pip install -r requirements.txt' dahulu.")
    sys.exit(1)

# ------------------------------------------------------------
# Konstanta & Path
# ------------------------------------------------------------
PROJECT_HOME = Path.home() / "BUGx"
HELP_DIR = PROJECT_HOME / "help_output"
WORDLIST_DIR = PROJECT_HOME / "wordlists"
SINGLES_DIR = PROJECT_HOME / "singletarget"
COMBO_DIR = PROJECT_HOME / "Kombinasitools"

# ------------------------------------------------------------
# Header renderer (tetap dari versi sebelumnya)
# ------------------------------------------------------------
TITLE_TEXT = "BUG-x"
TITLE_FONT = "slant"
FORGED_TEXT = "🧠 Forged by: D0Lv.1N"
CRAFTED_TEXT = "⚙️ Crafted by: GPT‑05"
_fig = Figlet(font=TITLE_FONT)


def _render_title_lines(text: str) -> List[str]:
    return _fig.renderText(text).rstrip("\n").splitlines()


def visual_width(text: str) -> int:
    total = 0
    for ch in text:
        code = ord(ch)
        if 0xFE00 <= code <= 0xFE0F:
            continue
        if unicodedata.combining(ch):
            continue
        east = unicodedata.east_asian_width(ch)
        total += 2 if east in ("F", "W") else 1
    return total


def pad_text(text: str, width: int, align: str = "center") -> str:
    vis_len = visual_width(text)
    if vis_len >= width:
        return text
    diff = width - vis_len
    if align == "left":
        return text + " " * diff
    if align == "right":
        return " " * diff + text
    left = diff // 2
    right = diff - left
    return " " * left + text + " " * right


def build_header(subtitle: str, version: str = "1.0") -> str:
    title_lines = _render_title_lines(TITLE_TEXT)
    width_of_title = max(visual_width(line) for line in title_lines)
    required_width = max(width_of_title, visual_width(subtitle), 60)
    inner_width = required_width
    box_width = inner_width + 2

    term_width = get_terminal_size((box_width, 20)).columns
    left_pad = max((term_width - box_width) // 2, 0)
    pad = " " * left_pad

    top = pad + "╔" + "═" * inner_width + "╗"
    bottom = pad + "╚" + "═" * inner_width + "╝"

    def row(text: str, align: str = "center") -> str:
        return pad + "║" + pad_text(text, inner_width, align) + "║"

    lines = [top]
    for line in title_lines:
        lines.append(row(line))
    lines.append(row(subtitle))
    lines.append(row(""))
    lines.append(row(pad_text(FORGED_TEXT, inner_width, "right")))

    crafted_width = visual_width(CRAFTED_TEXT)
    spacer_width = 1
    left_width = inner_width - crafted_width - spacer_width
    if left_width < 0:
        left_width = 0
    left_segment = pad_text(f"Version {version}", left_width, "left")
    right_segment = pad_text(CRAFTED_TEXT, crafted_width, "right")
    lines.append(pad + "║" + left_segment + " " * spacer_width + right_segment + "║")
    lines.append(bottom)
    return "\n".join(lines)


def print_header(subtitle: str, version: str = "1.0") -> None:
    print(build_header(subtitle, version))


# ------------------------------------------------------------
# Utilitas umum
# ------------------------------------------------------------
def ensure_venv_execution() -> None:
    """
    Jika dijalankan di luar venv, panggil ulang script menggunakan ~/venv/bin/python3.
    """
    if "VIRTUAL_ENV" in os.environ or os.environ.get("BUGX_NO_RECURSE") == "1":
        return

    venv_python = Path.home() / "venv" / "bin" / "python3"
    if not venv_python.exists():
        print("Venv global ~/venv tidak ditemukan. Jalankan 'python3 setup.py' terlebih dahulu.")
        sys.exit(1)

    env = os.environ.copy()
    env["BUGX_NO_RECURSE"] = "1"
    try:
        code = subprocess.call([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:], env=env)
    finally:
        subprocess.run(["clear"])
        print("SEMANGAT KAWAN 💪")
    sys.exit(code)


def clear_screen() -> None:
    subprocess.run(["clear"])


def slugify_target(raw: str) -> str:
    """
    Ubah domain/URL menjadi nama folder ringkas (tanpa TLD).
    """
    cleaned = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    cleaned = cleaned.split("/", 1)[0]
    if cleaned.startswith("www."):
        cleaned = cleaned[4:]
    parts = cleaned.split(".")
    if len(parts) > 1:
        cleaned = parts[0]
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in cleaned)
    return cleaned or "target"


def load_custom_flags(tool: str) -> List[Dict[str, str]]:
    """
    Baca file help_output/<tool>.json untuk daftar flag custom.
    """
    file_path = HELP_DIR / f"{tool}.json"
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    flags = data.get("parsed_flags") or []
    result = []
    seen = set()
    for item in flags:
        flag = (item.get("flag") or "").strip().rstrip(",")
        desc = (item.get("desc") or "").strip()
        if not flag.startswith("-") or flag in seen:
            continue
        seen.add(flag)
        result.append({"flag": flag, "desc": desc})
    return result


def expand_flags(flags: List[str]) -> List[str]:
    expanded: List[str] = []
    for item in flags:
        if not item:
            continue
        expanded.extend(shlex.split(item))
    return expanded


def join_flags_string(flags: List[str]) -> str:
    return " ".join(flags).strip()


def stream_process(command: CommandType, workdir: Path, shell: bool = False) -> int:
    """
    Jalankan command dan stream stdout/stderr ke terminal secara real-time.
    """
    process = subprocess.Popen(
        command,
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=shell,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line.rstrip())
    return process.wait()


def combine_unique_files(files: List[Path], destination: Path) -> int:
    """Gabungkan beberapa file menjadi satu dengan baris unik."""
    seen = set()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as out_f:
        for path in files:
            if not path or not path.exists():
                continue
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line in seen:
                        continue
                    seen.add(line)
                    out_f.write(line + "\n")
    return len(seen)


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        return sum(1 for line in fh if line.strip())


def ensure_url(target: str) -> str:
    if target.startswith("http://") or target.startswith("https://"):
        return target
    return f"https://{target}"


def run_gf_filter(pattern: str, source: Path, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which("gf"):
        shutil.copyfile(source, destination)
        return count_lines(destination)
    cmd = f"cat {shlex.quote(str(source))} | gf {pattern} > {shlex.quote(str(destination))}"
    rc = subprocess.run(cmd, shell=True)
    if rc.returncode != 0:
        shutil.copyfile(source, destination)
    return count_lines(destination)


def format_duration(seconds: float) -> str:
    total = int(seconds)
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def run_combo_tool(
    language: str,
    tool: str,
    target_value: str,
    focus_index: int,
    slug: str,
    combo_dir: Path,
    flags: Optional[List[str]] = None,
    custom_wordlists: Optional[List[str]] = None,
) -> Path:
    """Jalankan satu tool dalam workflow kombinasi dan tampilkan log singkat."""
    txt = TEXT[language]
    config = TOOL_CONFIGS.get(tool)
    if not config:
        raise ValueError(f"Tool {tool} belum dikonfigurasi")
    target_value = str(target_value)
    focus = config.focus_options[focus_index] if config.focus_options else FocusOption("Default", target_value, lambda _: True)
    flags_to_use = flags if flags is not None else config.default_flags[:]
    command, output_path, shell = build_command(
        tool,
        target_value,
        focus,
        flags_to_use,
        custom_wordlists,
        output_root=combo_dir,
        slug_override=slug,
    )
    if shell and isinstance(command, str):
        preview = command
    else:
        preview = " ".join(shlex.quote(c) for c in command)  # type: ignore[arg-type]
    print(f"\n🚀 {tool}: {preview}")
    rc = stream_process(command, Path.cwd(), shell=shell)
    status = "✅" if rc == 0 else f"⚠️ exit {rc}"
    print(f"   {status} -> {output_path}")
    return Path(output_path)


def execute_combo_workflow(choice: str, label: str, target: str, language: str) -> None:
    """Rangkai tahap demi tahap untuk workflow kombinasi tertentu."""
    slug = slugify_target(target)
    combo_dir = COMBO_DIR / slug
    combo_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    summary: List[str] = []

    try:
        if choice == "1":  # nuclei workflow
            print("\n🛠️ Stage 1: Enumerasi subdomain")
            subs_outputs = [
                run_combo_tool(language, "subfinder", target, 0, slug, combo_dir),
                run_combo_tool(language, "assetfinder", target, 0, slug, combo_dir),
                run_combo_tool(language, "amass", target, 0, slug, combo_dir),
            ]
            combined_subs = combo_dir / "subdomains_all.txt"
            sub_count = combine_unique_files(subs_outputs, combined_subs)

            print("\n🛠️ Stage 2: Resolusi & probing")
            dnsx_out = run_combo_tool(language, "dnsx", str(combined_subs), 0, slug, combo_dir)
            httpx_out = run_combo_tool(language, "httpx", str(dnsx_out), 0, slug, combo_dir)

            print("\n🛠️ Stage 3: Scan kerentanan")
            nuclei_out = run_combo_tool(language, "nuclei", str(httpx_out), 0, slug, combo_dir)

            summary = [
                f"📁 Folder combo    : {combo_dir}",
                f"🌐 Subdomain unik  : {sub_count}",
                f"🔎 Resolved hosts  : {count_lines(dnsx_out)}",
                f"⚡ Live URLs        : {count_lines(httpx_out)}",
                f"🚨 Temuan nuclei   : {count_lines(nuclei_out)}",
                f"📄 Report nuclei   : {nuclei_out}",
            ]

        elif choice == "2":  # dalfox + XSpear
            print("\n🛠️ Stage 1: Koleksi URL parameter")
            gau_out = run_combo_tool(language, "gau", target, 0, slug, combo_dir)
            param_out = run_combo_tool(language, "paramspider", target, 0, slug, combo_dir)
            combined_urls = combo_dir / "urls_all.txt"
            url_count = combine_unique_files([gau_out, param_out], combined_urls)

            print("\n🛠️ Stage 2: Filter kandidat XSS (gf xss)")
            xss_candidates = combo_dir / "xss_candidates.txt"
            cand_count = run_gf_filter("xss", combined_urls, xss_candidates)

            print("\n🛠️ Stage 3: Dalfox & XSpear")
            dalfox_out = run_combo_tool(language, "dalfox", str(xss_candidates), 1, slug, combo_dir)
            xspear_out = run_combo_tool(language, "XSpear", str(xss_candidates), 1, slug, combo_dir)

            summary = [
                f"📁 Folder combo    : {combo_dir}",
                f"🔗 URL unik         : {url_count}",
                f"🎯 Kandidat XSS     : {cand_count}",
                f"🛡️ Dalfox output    : {dalfox_out}",
                f"🛡️ XSpear output    : {xspear_out}",
            ]

        elif choice == "3":  # XSpear only
            print("\n🛠️ Stage 1: Koleksi URL parameter")
            gau_out = run_combo_tool(language, "gau", target, 0, slug, combo_dir)
            param_out = run_combo_tool(language, "paramspider", target, 0, slug, combo_dir)
            combined_urls = combo_dir / "urls_all.txt"
            url_count = combine_unique_files([gau_out, param_out], combined_urls)

            print("\n🛠️ Stage 2: Filter gf xss")
            xss_candidates = combo_dir / "xss_candidates.txt"
            cand_count = run_gf_filter("xss", combined_urls, xss_candidates)

            print("\n🛠️ Stage 3: XSpear")
            xspear_out = run_combo_tool(language, "XSpear", str(xss_candidates), 1, slug, combo_dir)

            summary = [
                f"📁 Folder combo    : {combo_dir}",
                f"🔗 URL unik         : {url_count}",
                f"🎯 Kandidat XSS     : {cand_count}",
                f"🛡️ XSpear output    : {xspear_out}",
            ]

        elif choice == "4":  # sqlmap sweep
            print("\n🛠️ Stage 1: Koleksi URL parameter")
            gau_out = run_combo_tool(language, "gau", target, 0, slug, combo_dir)
            combined_urls = combo_dir / "urls_all.txt"
            url_count = combine_unique_files([gau_out], combined_urls)

            print("\n🛠️ Stage 2: Filter gf sqli")
            sqli_candidates = combo_dir / "sqli_candidates.txt"
            cand_count = run_gf_filter("sqli", combined_urls, sqli_candidates)

            print("\n🛠️ Stage 3: sqlmap bulk")
            sqlmap_out = run_combo_tool(language, "sqlmap", str(sqli_candidates), 1, slug, combo_dir)

            summary = [
                f"📁 Folder combo    : {combo_dir}",
                f"🔗 URL unik         : {url_count}",
                f"🎯 Kandidat SQLi    : {cand_count}",
                f"🛡️ sqlmap output    : {sqlmap_out}",
            ]

        elif choice == "5":  # WordPress audit
            target_url = ensure_url(target)
            print("\n🛠️ Stage 1: Validasi host dengan httpx")
            httpx_out = run_combo_tool(language, "httpx", target_url, 1, slug, combo_dir)

            print("\n🛠️ Stage 2: WordPress Scan")
            wpscan_out = run_combo_tool(language, "wpscan", target_url, 0, slug, combo_dir)

            summary = [
                f"📁 Folder combo    : {combo_dir}",
                f"⚡ Live check       : {httpx_out}",
                f"🛡️ WPScan report    : {wpscan_out}",
            ]

        elif choice == "6":  # Exposure scan
            target_url = ensure_url(target)
            print("\n🛠️ Stage 1: Validasi host dengan httpx")
            httpx_out = run_combo_tool(language, "httpx", target_url, 1, slug, combo_dir)

            print("\n🛠️ Stage 2: xpoc")
            xpoc_out = run_combo_tool(language, "xpoc", target_url, 0, slug, combo_dir)

            summary = [
                f"📁 Folder combo    : {combo_dir}",
                f"⚡ Live check       : {httpx_out}",
                f"🛡️ xpoc report      : {xpoc_out}",
            ]

        else:
            summary = ["Workflow belum tersedia."]

    except Exception as exc:
        summary.append(f"⚠️ Terjadi error: {exc}")

    duration = format_duration(time.time() - start)
    print_header(f"{label} – {target}")
    for line in summary:
        print(line)
    print(f"{TEXT[language]['duration']} {duration}")
    print()


# ------------------------------------------------------------
# Bahasa & teks
# ------------------------------------------------------------
TEXT = {
    "id": {
        "lang_mode": "Pilihan Bahasa & Mode",
        "choose_language": "🌐 Pilih bahasa:",
        "choose_mode": "🚀 Pilih mode alat:",
        "mode_single": "Single tools",
        "mode_combo": "Kombinasi tools",
        "menu_exit": "[0] Keluar    [q] Kembali    [99] Menu utama",
        "pick_tool": "🛠️ Pilih tool:",
        "enter_choice": "Masukkan angka (default {default}): ",
        "input_target": "Masukkan target:",
        "input_domain_example": "✅ Contoh domain yang benar:",
        "input_url_example": "ℹ️ Contoh URL yang benar:",
        "input_file_example": "📂 Contoh file yang benar:",
        "focus_title": "🎯 Pilih fokus pencarian:",
        "flag_menu": "⚙️ Pilih konfigurasi flag:",
        "flag_standard": "Standard (rekomendasi BUG-x)",
        "flag_custom": "Custom (ambil dari help_output)",
        "flag_prompt": "Pilih flag (pisahkan dengan koma):",
        "flag_need_value": "📝 Flag {flag} butuh nilai.",
        "preview_title": "🔍 Preview command:",
        "proceed": "Lanjutkan? (y/n): ",
        "running": "Sedang berjalan:",
        "summary": "Ringkasan",
        "output_saved": "📁 Output disimpan:",
        "duration": "⏱️ Durasi:",
        "menu_return": "[99] Menu utama    [0] Keluar",
        "invalid_choice": "❌ Pilihan tidak valid.",
        "invalid_input": "❌ Format belum benar. Contoh:",
        "custom_wordlist": "Masukkan path wordlist custom:",
        "choose_focus": "🎯 Pilih fokus pencarian:",
    },
    "en": {
        "lang_mode": "Language & Mode Selection",
        "choose_language": "🌐 Choose language:",
        "choose_mode": "🚀 Select mode:",
        "mode_single": "Single tools",
        "mode_combo": "Combo workflows",
        "menu_exit": "[0] Exit    [q] Back    [99] Main menu",
        "pick_tool": "🛠️ Pick a tool:",
        "enter_choice": "Enter number (default {default}): ",
        "input_target": "Enter target:",
        "input_domain_example": "✅ Correct domain example:",
        "input_url_example": "ℹ️ Correct URL example:",
        "input_file_example": "📂 Correct file example:",
        "focus_title": "🎯 Select focus:",
        "flag_menu": "⚙️ Choose flag configuration:",
        "flag_standard": "Standard (BUG-x recomended)",
        "flag_custom": "Custom (from help_output)",
        "flag_prompt": "Select flags (comma separated):",
        "flag_need_value": "📝 Flag {flag} requires a value.",
        "preview_title": "🔍 Command preview:",
        "proceed": "Proceed? (y/n): ",
        "running": "Running:",
        "summary": "Summary",
        "output_saved": "📁 Output saved:",
        "duration": "⏱️ Duration:",
        "menu_return": "[99] Main menu    [0] Exit",
        "invalid_choice": "❌ Invalid choice.",
        "invalid_input": "❌ Input format invalid. Example:",
        "custom_wordlist": "Enter custom wordlist path:",
        "choose_focus": "🎯 Select focus:",
    },
}


# ------------------------------------------------------------
# Tool configuration
# ------------------------------------------------------------

Validator = Callable[[str], bool]
CommandBuilder = Callable[[Dict[str, str]], Tuple[List[str], str]]


def validate_contains_fuzz(url: str) -> bool:
    return "FUZZ" in url


def validate_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def validate_domain(domain: str) -> bool:
    return "." in domain and " " not in domain and "/" not in domain


def validate_file(path: str) -> bool:
    return Path(path).expanduser().exists()


def validate_list_file(path: str) -> bool:
    file_path = Path(path).expanduser()
    return file_path.exists() and file_path.is_file() and file_path.stat().st_size > 0


def validate_ip_or_cidr(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    allowed = set("0123456789./:,")
    return set(value) <= allowed and any(ch.isdigit() for ch in value)


@dataclass
class FocusOption:
    label: str
    example: str
    validator: Validator
    is_file: bool = False
    wordlists: List[str] = field(default_factory=list)
    extra_args: List[str] = field(default_factory=list)


@dataclass
class ToolConfig:
    command: str
    descriptions: Dict[str, str]
    focus_options: List[FocusOption] = field(default_factory=list)
    default_flags: List[str] = field(default_factory=list)
    value_flags: Dict[str, str] = field(default_factory=dict)  # flag -> prompt contoh
    needs_output_json: bool = True
    custom_handler: Optional[CommandBuilder] = None


TOOL_ORDER = [
    "subfinder",
    "assetfinder",
    "amass",
    "gau",
    "waybackurls",
    "httpx",
    "naabu",
    "dnsx",
    "nuclei",
    "ffuf",
    "feroxbuster",
    "gobuster",
    "gospider",
    "httprobe",
    "sqlmap",
    "masscan",
    "nmap",
    "whatweb",
    "wpscan",
    "eyewitness",
    "subjack",
    "sublister",
    "shuffledns",
    "dalfox",
    "gowitness",
    "XSpear",
    "xpoc",
    "paramspider",
]


# Konfigurasi detail untuk tiap tool single (flag default, fokus input, dll).
TOOL_CONFIGS: Dict[str, ToolConfig] = {
    "subfinder": ToolConfig(
        command="subfinder",
        descriptions={"id": "Enumerasi subdomain pasif cepat", "en": "Passive subdomain enumeration"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain)],
        default_flags=["-all", "-recursive", "-silent"],
    ),
    "assetfinder": ToolConfig(
        command="assetfinder",
        descriptions={"id": "Sumber subdomain tambahan", "en": "Alternate passive subdomain sources"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain)],
        default_flags=["--subs-only"],
    ),
    "amass": ToolConfig(
        command="amass",
        descriptions={"id": "Enum subdomain kaya fitur", "en": "Feature-rich subdomain enumeration"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain)],
        default_flags=["enum", "-passive"],
    ),
    "gau": ToolConfig(
        command="gau",
        descriptions={"id": "Kumpulkan URL historis", "en": "Collect historical URLs"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain)],
        default_flags=["--subs"],
    ),
    "waybackurls": ToolConfig(
        command="waybackurls",
        descriptions={"id": "Arsip Wayback Machine", "en": "Wayback Machine URL fetcher"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain)],
    ),
    "httpx": ToolConfig(
        command="httpx",
        descriptions={"id": "Probe host HTTP/HTTPS", "en": "HTTP probing engine"},
        focus_options=[
            FocusOption("File list host", str(SINGLES_DIR / "target" / "live_hosts.txt"), validate_list_file, is_file=True),
            FocusOption("Single host", "https://target.com", validate_url),
        ],
        default_flags=["-title", "-sc", "-cl", "-td", "-ip", "-cname", "-silent"],
        value_flags={"-H": "Authorization: Bearer TOKEN", "-mc": "200,302", "-t": "50"},
    ),
    "naabu": ToolConfig(
        command="naabu",
        descriptions={"id": "Port scan TCP cepat", "en": "Fast TCP port scanner"},
        focus_options=[
            FocusOption("Satu host/IP", "scanme.nmap.org", validate_domain),
            FocusOption("File daftar host", str(SINGLES_DIR / "target" / "hosts.txt"), validate_list_file, is_file=True),
        ],
        default_flags=["-top-ports 1000", "-rate 1000", "-silent"],
    ),
    "dnsx": ToolConfig(
        command="dnsx",
        descriptions={"id": "Resolver DNS + wildcard check", "en": "DNS resolver with wildcard detection"},
        focus_options=[
            FocusOption(
                "File subdomain",
                str(SINGLES_DIR / "target" / "subdomains.txt"),
                validate_list_file,
                is_file=True,
                wordlists=["subdomains.txt", "resolvers.txt"],
            )
        ],
        default_flags=["-resp", "-silent"],
    ),
    "nuclei": ToolConfig(
        command="nuclei",
        descriptions={"id": "Template-based vulnerability scanner", "en": "Template-based vulnerability scanner"},
        focus_options=[
            FocusOption(
                "File URL list",
                str(SINGLES_DIR / "target" / "httpx_live.txt"),
                validate_list_file,
                is_file=True,
            )
        ],
        default_flags=["-severity medium,high,critical", "-c 50", "-duc"],
        value_flags={"-tags": "cves,exposed-panels"},
    ),
    "ffuf": ToolConfig(
        command="ffuf",
        descriptions={"id": "Fuzzing endpoint, parameter, dan API", "en": "Fast web fuzzing utility"},
        focus_options=[
            FocusOption("Directory fuzzing", "https://target.com/FUZZ", validate_contains_fuzz, wordlists=["directories.txt"]),
            FocusOption("API endpoint fuzzing", "https://api.target.com/v1/FUZZ", validate_contains_fuzz, wordlists=["apis.txt"]),
            FocusOption("Parameter / XSS fuzzing", "https://target.com/search?q=FUZZ", validate_contains_fuzz, wordlists=["params.txt", "xss.txt"]),
        ],
        default_flags=["-mc 200,302", "-t 50"],
        value_flags={"-H": "Authorization: Bearer TOKEN", "-mc": "200,302", "-fs": "0", "-t": "40", "-timeout": "10", "-p": "0.1-0.5"},
    ),
    "feroxbuster": ToolConfig(
        command="feroxbuster",
        descriptions={"id": "Bruteforce direktori multithread", "en": "Multithreaded directory brute-forcing"},
        focus_options=[
            FocusOption("URL dengan trailing slash", "https://target.com/", validate_url, wordlists=["directories.txt"])
        ],
        default_flags=["-k", "-t 40", "-q"],
    ),
    "gobuster": ToolConfig(
        command="gobuster",
        descriptions={"id": "Gobuster mode directory", "en": "Gobuster directory mode"},
        focus_options=[
            FocusOption("URL dengan trailing slash", "https://target.com/", validate_url, wordlists=["directories.txt"])
        ],
        default_flags=["dir", "-t 50", "-b 204,301,302,403"],
        value_flags={"-x": "php,asp,aspx"},
    ),
    "gospider": ToolConfig(
        command="gospider",
        descriptions={"id": "Crawler untuk endpoint baru", "en": "Crawler to discover endpoints"},
        focus_options=[FocusOption("Domain atau URL", "https://target.com", validate_url)],
        default_flags=["-c 10", "-d 2"],
        needs_output_json=False,
    ),
    "httprobe": ToolConfig(
        command="httprobe",
        descriptions={"id": "Verifikasi host HTTP/HTTPS", "en": "Probe host for HTTP/HTTPS"},
        focus_options=[FocusOption("File subdomain", str(SINGLES_DIR / "target" / "subdomains.txt"), validate_list_file, is_file=True)],
        needs_output_json=False,
    ),
    "sqlmap": ToolConfig(
        command="sqlmap",
        descriptions={"id": "SQL injection automation", "en": "SQL injection automation"},
        focus_options=[
            FocusOption("URL dengan parameter", "https://target.com/item?id=1", validate_url),
            FocusOption("File URL list", str(SINGLES_DIR / "target" / "sqli_targets.txt"), validate_list_file, is_file=True),
        ],
        default_flags=["--batch", "--risk 2", "--level 2"],
        value_flags={"--tamper": "between,randomcase"},
        needs_output_json=False,
    ),
    "masscan": ToolConfig(
        command="masscan",
        descriptions={"id": "Port scanner sangat cepat", "en": "Ultra-fast port scanner"},
        focus_options=[FocusOption("IP / CIDR", "192.168.0.0/24", validate_ip_or_cidr)],
        default_flags=["-p1-65535", "--rate 10000"],
    ),
    "nmap": ToolConfig(
        command="nmap",
        descriptions={"id": "Nmap service & version scan", "en": "Service & version detection"},
        focus_options=[
            FocusOption("Single host", "scanme.nmap.org", validate_domain),
            FocusOption("File host list", str(SINGLES_DIR / "target" / "hosts.txt"), validate_list_file, is_file=True),
        ],
        default_flags=["-sV", "-T4", "-Pn"],
        needs_output_json=False,
    ),
    "whatweb": ToolConfig(
        command="whatweb",
        descriptions={"id": "Fingerprint teknologi web", "en": "Web technology fingerprinting"},
        focus_options=[FocusOption("URL", "https://target.com", validate_url)],
        default_flags=["-a 3"],
        needs_output_json=False,
    ),
    "wpscan": ToolConfig(
        command="wpscan",
        descriptions={"id": "Audit keamanan WordPress", "en": "WordPress security audit"},
        focus_options=[FocusOption("URL WordPress", "https://wp.target.com", validate_url)],
        default_flags=["--enumerate vp,vt,u", "--random-user-agent"],
    ),
    "eyewitness": ToolConfig(
        command="eyewitness",
        descriptions={"id": "Screenshot massal host hidup", "en": "Take screenshots of live hosts"},
        focus_options=[
            FocusOption("File URL list", str(SINGLES_DIR / "target" / "httpx_live.txt"), validate_list_file, is_file=True),
            FocusOption("Single URL", "https://admin.target.com", validate_url),
        ],
        default_flags=["--web"],
        needs_output_json=False,
    ),
    "subjack": ToolConfig(
        command="subjack",
        descriptions={"id": "Deteksi subdomain takeover", "en": "Detect potential subdomain takeover"},
        focus_options=[FocusOption("File subdomain", str(SINGLES_DIR / "target" / "subdomains.txt"), validate_list_file, is_file=True)],
        default_flags=["-t 100", "-timeout 30", "-ssl"],
    ),
    "sublister": ToolConfig(
        command="sublister",
        descriptions={"id": "Sublist3r enumerasi subdomain", "en": "Sublist3r subdomain enumeration"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain)],
        default_flags=["-t 20"],
    ),
    "shuffledns": ToolConfig(
        command="shuffledns",
        descriptions={"id": "Resolver DNS + wildcard check", "en": "DNS resolver with wildcard detection"},
        focus_options=[
            FocusOption(
                "File subdomain",
                str(SINGLES_DIR / "target" / "subdomains.txt"),
                validate_list_file,
                is_file=True,
                wordlists=["subdomains.txt", "resolvers.txt"],
            )
        ],
        default_flags=["-silent"],
        value_flags={"-d": "example.com"},
    ),
    "dalfox": ToolConfig(
        command="dalfox",
        descriptions={"id": "Fuzz XSS pintar", "en": "Smart XSS fuzzing"},
        focus_options=[
            FocusOption("URL parameter", "https://target.com/search?q=FUZZ", validate_contains_fuzz, wordlists=["xss.txt"]),
            FocusOption("File URL list", str(SINGLES_DIR / "target" / "xss_candidates.txt"), validate_list_file, is_file=True, wordlists=["xss.txt"]),
        ],
        default_flags=["--silence", "--deep-dom"],
        value_flags={"--cookie": "session=TOKEN"},
    ),
    "gowitness": ToolConfig(
        command="gowitness",
        descriptions={"id": "Inventory & screenshot web", "en": "Web screenshots & inventory"},
        focus_options=[
            FocusOption("File URL list", str(SINGLES_DIR / "target" / "httpx_live.txt"), validate_list_file, is_file=True),
            FocusOption("Single URL", "https://target.com", validate_url),
        ],
        needs_output_json=False,
    ),
    "XSpear": ToolConfig(
        command="XSpear",
        descriptions={"id": "Scanner XSS otomatis", "en": "Automated XSS scanner"},
        focus_options=[
            FocusOption("URL parameter", "https://target.com/search?q=FUZZ", validate_contains_fuzz, wordlists=["xss.txt"]),
            FocusOption("File URL list", str(SINGLES_DIR / "target" / "xss_candidates.txt"), validate_list_file, is_file=True, wordlists=["xss.txt"]),
        ],
        default_flags=["-q"],
    ),
    "xpoc": ToolConfig(
        command="xpoc",
        descriptions={"id": "Scan exposure & misconfig", "en": "Exposure / misconfiguration scanner"},
        focus_options=[FocusOption("Target URL/host", "https://target.com", validate_url)],
        default_flags=[],
    ),
    "paramspider": ToolConfig(
        command="paramspider",
        descriptions={"id": "Kumpulkan parameter URL", "en": "Collect URL parameters"},
        focus_options=[FocusOption("Domain", "example.com", validate_domain, wordlists=["params.txt"])],
        default_flags=["--exclude woff,css,png"],
        needs_output_json=False,
    ),
}

# Tool default: for tool yang belum memiliki konfigurasi spesifik
DEFAULT_TOOL_DESCRIPTION = "Tool belum memiliki konfigurasi khusus. Masukkan command manual."


# ------------------------------------------------------------
# Fungsi pemilihan & jalankan
# ------------------------------------------------------------
def prompt_input(prompt: str) -> str:
    try:
        return input(prompt)
    except KeyboardInterrupt:
        print()
        return ""


def choose_language_and_mode() -> Tuple[str, str]:
    clear_screen()
    subtitle = "Pilihan Bahasa & Mode / Language & Mode"
    print_header(subtitle)

    lang_choice = prompt_input(
        "\n🌐 Pilih bahasa / Choose language:\n"
        " 1) Indonesia\n"
        " 2) English\n\n"
        "⌨️ Masukkan angka (default 1): "
    ).strip()
    language = "en" if lang_choice == "2" else "id"
    txt = TEXT[language]

    prompt = (
        f"\n{txt['choose_mode']}\n"
        f" 1) {txt['mode_single']}\n"
        f" 2) {txt['mode_combo']}\n\n"
        f"{txt['menu_exit']}\n\n"
        f"⌨️ Masukkan angka mode (default 1): "
    )
    while True:
        choice = prompt_input(prompt).strip()
        if choice in ("0", "q", "Q"):
            clear_screen()
            print("SEMANGAT KAWAN 💪")
            sys.exit(0)
        if choice in ("", "1", "2"):
            mode = "combo" if choice == "2" else "single"
            return language, mode
        print(TEXT[language]["invalid_choice"])


def list_single_tools(language: str) -> str:
    txt = TEXT[language]
    clear_screen()
    print_header(f"{txt['mode_single']} ({'English' if language=='en' else 'Indonesia'})")
    lines = []
    for idx, tool in enumerate([t for t in TOOL_ORDER if t in TOOL_CONFIGS], start=1):
        config = TOOL_CONFIGS[tool]
        desc = config.descriptions.get(language, config.descriptions.get("en", ""))
        lines.append(f" {idx:>2}) {tool:<12} – {desc}")
    print("\n".join(lines))
    print(f"\n{txt['menu_exit']}")
    tool_choice = prompt_input(f"\nEnter tool number: ").strip()
    if tool_choice in ("0", "q", "Q"):
        clear_screen()
        print("SEMANGAT KAWAN 💪")
        sys.exit(0)
    if tool_choice == "99":
        return "MENU"
    try:
        idx = int(tool_choice)
    except ValueError:
        print(txt["invalid_choice"])
        return ""
    tools_sorted = [t for t in TOOL_ORDER if t in TOOL_CONFIGS]
    if 1 <= idx <= len(tools_sorted):
        return tools_sorted[idx - 1]
    print(txt["invalid_choice"])
    return ""


def choose_focus(language: str, config: ToolConfig) -> Tuple[FocusOption, Optional[List[str]]]:
    txt = TEXT[language]
    focus_list = config.focus_options
    custom_wordlist = None

    while True:
        print(f"\n{txt['focus_title']}")
        for idx, opt in enumerate(focus_list, start=1):
            wl_text = ""
            if opt.wordlists:
                wl_text = f" (wordlist: {', '.join(opt.wordlists)})"
            print(f" {idx}) {opt.label}{wl_text}")
        allow_custom = focus_list and any(opt.wordlists for opt in focus_list)
        if allow_custom:
            print(f" 4) Custom wordlist")
        choice = prompt_input("\n" + txt["enter_choice"].format(default=1)).strip()
        if choice in ("", "1", "2", "3"):
            idx = int(choice) if choice else 1
            if 1 <= idx <= len(focus_list):
                return focus_list[idx - 1], None
        elif choice == "4" and allow_custom:
            focus = focus_list[0]
            custom_path = prompt_input(f"\n{txt['custom_wordlist']} ").strip()
            if custom_path:
                custom_wordlist = [str(Path(custom_path).expanduser())]
                return focus, custom_wordlist
        print(txt["invalid_choice"])


def prompt_target(language: str, option: FocusOption) -> str:
    txt = TEXT[language]
    example_label = txt["input_file_example"] if option.is_file else (
        txt["input_url_example"] if option.validator in (validate_contains_fuzz, validate_url) else txt["input_domain_example"]
    )
    while True:
        print(f"\n{example_label}\n  {option.example}\n")
        value = prompt_input(f"{txt['input_target']} ").strip()
        if option.validator(value):
            return value
        print(f"{txt['invalid_input']}\n  {option.example}")


def choose_flags(language: str, tool: str, config: ToolConfig) -> List[str]:
    txt = TEXT[language]
    print(f"\n{txt['flag_menu']}\n 1) {txt['flag_standard']}\n 2) {txt['flag_custom']}\n")
    choice = prompt_input("Masukkan angka (default 1): ").strip()
    if choice not in ("2",):
        return config.default_flags[:]

    flags = load_custom_flags(tool)
    if not flags:
        print("⚠️ Custom flag tidak tersedia, menggunakan mode standard.")
        return config.default_flags[:]

    print("\n📚 Flag tersedia:")
    for idx, item in enumerate(flags, start=1):
        desc = f" – {item['desc']}" if item["desc"] else ""
        print(f" {idx}) {item['flag']}{desc}")

    selected = prompt_input(f"\n{txt['flag_prompt']} ").strip()
    if not selected:
        return config.default_flags[:]

    chosen_flags = []
    for token in selected.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token)
        except ValueError:
            continue
        if 1 <= idx <= len(flags):
            flag = flags[idx - 1]["flag"]
            if flag in config.value_flags:
                prompt = txt["flag_need_value"].format(flag=flag)
                example = config.value_flags[flag]
                value = prompt_input(f"{prompt} (contoh: {example})\n> ").strip()
                if value:
                    chosen_flags.append(f"{flag} {value}")
                else:
                    chosen_flags.append(flag)
            else:
                chosen_flags.append(flag)
    return chosen_flags or config.default_flags[:]


def build_command(
    tool: str,
    target: str,
    focus: FocusOption,
    flags: List[str],
    custom_wordlists: Optional[List[str]],
    output_root: Path = SINGLES_DIR,
    slug_override: Optional[str] = None,
) -> Tuple[CommandType, Path, bool]:
    """
    Susun command akhir dan path output.
    """
    config = TOOL_CONFIGS[tool]
    slug_name = slug_override or slugify_target(target)
    output_dir = output_root / slug_name
    output_dir.mkdir(parents=True, exist_ok=True)
    shell = False
    flags_expanded = expand_flags(flags)
    wordlists = custom_wordlists or focus.wordlists

    def wl_path(name: str) -> Path:
        candidate = Path(name).expanduser()
        if candidate.exists():
            return candidate
        return WORDLIST_DIR / name

    # --- Tool-specific command builders ---
    if tool == "subfinder":
        outfile = output_dir / "subfinder.txt"
        command = [config.command, "-d", target] + flags_expanded + ["-o", str(outfile)]
        return command, outfile, shell

    if tool == "assetfinder":
        outfile = output_dir / "assetfinder.txt"
        flag_str = join_flags_string(flags_expanded)
        flag_part = f"{flag_str} " if flag_str else ""
        cmd = f"assetfinder --subs-only {flag_part}{shlex.quote(target)} > {shlex.quote(str(outfile))}"
        return cmd, outfile, True

    if tool == "amass":
        outfile = output_dir / "amass.txt"
        command = [config.command] + flags_expanded + ["-d", target, "-o", str(outfile)]
        return command, outfile, shell

    if tool == "gau":
        outfile = output_dir / "gau.txt"
        flag_str = join_flags_string(flags_expanded)
        flag_part = f"{flag_str} " if flag_str else ""
        cmd = f"gau {flag_part}{shlex.quote(target)} > {shlex.quote(str(outfile))}"
        return cmd, outfile, True

    if tool == "waybackurls":
        outfile = output_dir / "waybackurls.txt"
        flag_str = join_flags_string(flags_expanded)
        cmd = (
            f"echo {shlex.quote(target)} | waybackurls {flag_str} > {shlex.quote(str(outfile))}"
            if flag_str
            else f"echo {shlex.quote(target)} | waybackurls > {shlex.quote(str(outfile))}"
        )
        return cmd, outfile, True

    if tool == "httpx":
        outfile = output_dir / "httpx.txt"
        command = [config.command]
        if focus.is_file:
            command.extend(["-l", target])
        else:
            command.extend(["-u", target])
        command.extend(flags_expanded)
        command.extend(["-o", str(outfile)])
        return command, outfile, shell

    if tool == "naabu":
        outfile = output_dir / "naabu.txt"
        command = [config.command]
        if focus.is_file:
            command.extend(["-list", target])
        else:
            command.extend(["-host", target])
        command.extend(flags_expanded)
        command.extend(["-o", str(outfile)])
        return command, outfile, shell

    if tool == "dnsx":
        outfile = output_dir / "dnsx.txt"
        command = [config.command]
        command.extend(["-l", target, "-r", str(wl_path("resolvers.txt"))])
        command.extend(flags_expanded)
        command.extend(["-o", str(outfile)])
        return command, outfile, shell

    if tool == "nuclei":
        outfile = output_dir / "nuclei.json"
        templates_dir = Path.home() / "nuclei-templates"
        command = [config.command, "-l", target, "-o", str(outfile)]
        if templates_dir.exists():
            command.extend(["-t", str(templates_dir)])
        command.extend(flags_expanded)
        return command, outfile, shell

    if tool == "ffuf":
        outfile = output_dir / "ffuf.json"
        command = [config.command, "-u", target]
        for wl in wordlists:
            command.extend(["-w", str(wl_path(wl))])
        command.extend(flags_expanded)
        command.extend(["-o", str(outfile)])
        return command, outfile, shell

    if tool == "feroxbuster":
        outfile = output_dir / "feroxbuster.txt"
        command = [config.command, "-u", target]
        for wl in wordlists:
            command.extend(["-w", str(wl_path(wl))])
        command.extend(flags_expanded)
        command.extend(["-o", str(outfile)])
        return command, outfile, shell

    if tool == "gobuster":
        outfile = output_dir / "gobuster.txt"
        command = [config.command] + flags_expanded + ["-u", target]
        for wl in wordlists:
            command.extend(["-w", str(wl_path(wl))])
        command.extend(["-o", str(outfile)])
        return command, outfile, shell

    if tool == "gospider":
        out_dir = output_dir / "gospider"
        out_dir.mkdir(parents=True, exist_ok=True)
        command = [config.command, "-s", target, "-o", str(out_dir)] + flags_expanded
        return command, out_dir, shell

    if tool == "httprobe":
        outfile = output_dir / "httprobe.txt"
        flag_str = join_flags_string(flags_expanded)
        cmd = (
            f"cat {shlex.quote(target)} | httprobe {flag_str} > {shlex.quote(str(outfile))}"
            if flag_str
            else f"cat {shlex.quote(target)} | httprobe > {shlex.quote(str(outfile))}"
        )
        return cmd, outfile, True

    if tool == "sqlmap":
        out_dir = output_dir / "sqlmap"
        out_dir.mkdir(parents=True, exist_ok=True)
        command = [config.command] + flags_expanded
        if focus.is_file:
            command.extend(["-m", target])
        else:
            command.extend(["-u", target])
        command.extend(["--output-dir", str(out_dir)])
        return command, out_dir, shell

    if tool == "masscan":
        outfile = output_dir / "masscan.txt"
        command = [config.command, target] + flags_expanded + ["-oL", str(outfile)]
        return command, outfile, shell

    if tool == "nmap":
        base = output_dir / "nmap"
        command = [config.command] + flags_expanded
        if focus.is_file:
            command.extend(["-iL", target])
        else:
            command.append(target)
        command.extend(["-oA", str(base)])
        return command, base.with_suffix(".nmap"), shell

    if tool == "whatweb":
        outfile = output_dir / "whatweb.json"
        command = [config.command, target] + flags_expanded + ["--log-json", str(outfile)]
        return command, outfile, shell

    if tool == "wpscan":
        outfile = output_dir / "wpscan.txt"
        command = [config.command, "--url", target] + flags_expanded + ["--output", str(outfile)]
        return command, outfile, shell

    if tool == "eyewitness":
        temp_dir = output_dir / "eyewitness"
        temp_dir.mkdir(parents=True, exist_ok=True)
        command = [config.command]
        if focus.is_file:
            command.extend(["--web", "--threads", "20", "--prepend-https", "-f", target])
        else:
            command.extend(["--web", "--threads", "20", "--prepend-https", "-u", target])
        command.extend(flags_expanded)
        command.extend(["-d", str(temp_dir)])
        return command, temp_dir, shell

    if tool == "subjack":
        outfile = output_dir / "subjack.txt"
        command = [config.command, "-w", target, "-o", str(outfile)] + flags_expanded
        return command, outfile, shell

    if tool == "sublister":
        outfile = output_dir / "sublister.txt"
        command = [config.command, "-d", target, "-o", str(outfile)] + flags_expanded
        return command, outfile, shell

    if tool == "shuffledns":
        outfile = output_dir / "shuffledns.txt"
        command = [config.command, "-list", target, "-r", str(wl_path("resolvers.txt")), "-o", str(outfile)] + flags_expanded
        return command, outfile, shell

    if tool == "dalfox":
        outfile = output_dir / "dalfox.txt"
        command = [config.command]
        if focus.is_file:
            command.extend(["file", "--input", target])
        else:
            command.extend(["url", target])
        command.extend(flags_expanded)
        command.extend(["--output", str(outfile)])
        for wl in wordlists:
            command.extend(["-w", str(wl_path(wl))])
        return command, outfile, shell

    if tool == "gowitness":
        out_dir = output_dir / "gowitness"
        out_dir.mkdir(parents=True, exist_ok=True)
        if focus.is_file:
            command = [config.command, "file", "-f", target, "--destination", str(out_dir)] + flags_expanded
        else:
            command = [config.command, "single", "-u", target, "--destination", str(out_dir)] + flags_expanded
        return command, out_dir, shell

    if tool == "XSpear":
        outfile = output_dir / "XSpear.txt"
        command = [config.command]
        if focus.is_file:
            command.extend(["-f", target])
        else:
            command.extend(["-u", target])
        command.extend(flags_expanded)
        command.extend(["-o", str(outfile)])
        for wl in wordlists:
            command.extend(["-w", str(wl_path(wl))])
        return command, outfile, shell

    if tool == "xpoc":
        outfile = output_dir / "xpoc.json"
        command = [config.command, "scan", "--url", target, "-o", str(outfile)] + flags_expanded
        return command, outfile, shell

    if tool == "paramspider":
        outfile = output_dir / "paramspider.txt"
        command = [config.command, "--domain", target, "--output", str(outfile)] + flags_expanded
        return command, outfile, shell

    # fallback generic
    outfile = output_dir / f"{tool}.out"
    command = [config.command] + flags_expanded
    return command, outfile, shell


def run_single_tool(language: str) -> None:
    while True:
        tool = list_single_tools(language)
        if not tool:
            continue
        if tool == "MENU":
            return
        config = TOOL_CONFIGS.get(tool)
        if not config:
            print("Tool belum dikonfigurasi.")
            continue

        clear_screen()
        print_header(f"Tool: {tool}")
        focus, custom_wordlists = choose_focus(language, config) if config.focus_options else (
            FocusOption(label="Default", example="example.com", validator=validate_domain),
            None,
        )
        target = prompt_target(language, focus)
        flags = choose_flags(language, tool, config)
        command, output_path, shell = build_command(tool, target, focus, flags, custom_wordlists)

        txt = TEXT[language]
        if shell and isinstance(command, str):
            preview_cmd = command
        else:
            preview_cmd = " ".join(shlex.quote(c) for c in command)  # type: ignore[arg-type]
        print(f"\n{txt['preview_title']}\n{preview_cmd}\n")
        proceed = prompt_input(txt["proceed"]).strip().lower()
        if proceed != "y":
            print("❎ Dibatalkan.")
            return

        clear_screen()
        print_header(f"{tool} – Running")
        print(f"{txt['running']} {preview_cmd}\n")
        rc = stream_process(command, Path.cwd(), shell=shell)
        status = "✅" if rc == 0 else f"⚠️ exit code {rc}"

        print_header(f"{txt['summary']} – {tool} ({status})")
        print(f"📊 Target       : {target}")
        print(f"🔧 Flags        : {' '.join(flags) if flags else '-'}")
        print(f"{txt['output_saved']} {output_path}")
        print(f"{txt['menu_return']}")

        choice = prompt_input("> ").strip()
        if choice == "0":
            clear_screen()
            print("SEMANGAT KAWAN 💪")
            sys.exit(0)
        if choice == "99":
            return


# ------------------------------------------------------------
# Mode kombinasi (outline sederhana)
# ------------------------------------------------------------
ComboMode = Tuple[str, List[str]]

COMBO_WORKFLOWS: Dict[str, ComboMode] = {
    "1": ("Pindai Permukaan Kerentanan", ["nuclei"]),
    "2": ("Perburuan Parameter XSS", ["dalfox", "XSpear"]),
    "3": ("Probe XSS Lanjutan", ["XSpear"]),
    "4": ("Sapu SQL Injection", ["sqlmap"]),
    "5": ("Audit Keamanan WordPress", ["wpscan"]),
    "6": ("Pindai Jejak Eksposur", ["xpoc"]),
}


def run_combo_mode(language: str) -> None:
    txt = TEXT[language]
    clear_screen()
    print_header(f"Mode: {txt['mode_combo']}")
    print("⚔️ Pilih workflow otomatis:")
    for key, (label, _) in COMBO_WORKFLOWS.items():
        print(f" {key}) {label}")
    print(f"\n{txt['menu_exit']}")
    choice = prompt_input("\n⌨️ Masukkan angka workflow (default 1): ").strip() or "1"
    if choice in ("0", "q", "Q"):
        clear_screen()
        print("SEMANGAT KAWAN 💪")
        sys.exit(0)
    if choice == "99":
        return
    if choice not in COMBO_WORKFLOWS:
        print(txt["invalid_choice"])
        return
    label, _ = COMBO_WORKFLOWS[choice]

    print("\n🎯 Target mode:")
    print(" 1) Single domain")
    print(" 2) File daftar domain")
    target_mode = prompt_input("\n" + txt["enter_choice"].format(default=1)).strip()
    targets: List[str] = []
    if target_mode == "2":
        file_focus = FocusOption("Daftar domain", str(Path.home() / "targets.txt"), validate_list_file, is_file=True)
        file_path = prompt_target(language, file_focus)
        seen_targets = set()
        with Path(file_path).open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                domain = line.strip()
                if not domain:
                    continue
                if domain not in seen_targets:
                    seen_targets.add(domain)
                    targets.append(domain)
        if not targets:
            print("❌ File tidak memiliki domain valid.")
            return
    else:
        domain_focus = FocusOption("Domain", "example.com", validate_domain)
        targets.append(prompt_target(language, domain_focus))

    for domain in targets:
        execute_combo_workflow(choice, label, domain, language)

    print(f"\n{txt['menu_return']}")
    final_choice = prompt_input("> ").strip()
    if final_choice == "0":
        clear_screen()
        print("SEMANGAT KAWAN 💪")
        sys.exit(0)


# ------------------------------------------------------------
# Main CLI loop
# ------------------------------------------------------------
def main() -> None:
    ensure_venv_execution()
    SINGLES_DIR.mkdir(parents=True, exist_ok=True)
    COMBO_DIR.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            language, mode = choose_language_and_mode()
            if mode == "single":
                run_single_tool(language)
            else:
                run_combo_mode(language)
    except KeyboardInterrupt:
        print("\n^C")
    finally:
        clear_screen()
        print("SEMANGAT KAWAN 💪")


if __name__ == "__main__":
    main()
