#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse

# --- Configuration & Constants ---
BUGX_ROOT = os.path.expanduser("~/BUGx")
BIN_DIR = os.path.join(BUGX_ROOT, "bin")
TMP_DIR = os.path.join(BUGX_ROOT, "tmp")
RESULTS_DIR = os.path.join(BUGX_ROOT, "results")
LOGS_DIR = os.path.join(BUGX_ROOT, "logs")
WORDLISTS_DIR = os.path.join(BUGX_ROOT, "wordlists")

# Ensure necessary directories exist
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ANSI Color Codes
C_RESET = "\033[0m"
C_RED = "\033[0;31m"
C_GREEN = "\033[0;32m"
C_YELLOW = "\033[0;33m"
C_BLUE = "\033[0;34m"
C_MAGENTA = "\033[0;35m"
C_CYAN = "\033[0;36m"
C_BOLD = "\033[1m"
C_LIGHT_GRAY = "\033[0;90m"
C_BRIGHT_RED = "\033[1;31m"
C_BRIGHT_GREEN = "\033[1;32m"
C_BRIGHT_YELLOW = "\033[1;33m"
C_BRIGHT_BLUE = "\033[1;34m"
C_BRIGHT_MAGENTA = "\033[1;35m"
C_BRIGHT_CYAN = "\033[1;36m"
C_ORANGE = "\033[38;5;208m"
C_PURPLE = "\033[38;5;135m"
C_PINK = "\033[38;5;213m"

# Symbols & Icons
SYMBOL_SUCCESS = "✓"
SYMBOL_ERROR = "✗"
SYMBOL_WARNING = "⚠"
SYMBOL_INFO = "ℹ"
SYMBOL_ROCKET = "🚀"
SYMBOL_TARGET = "🎯"
SYMBOL_TOOL = "🔧"
SYMBOL_SCAN = "🔍"
SYMBOL_FIRE = "🔥"
SYMBOL_CLOCK = "⏱"
SYMBOL_ARROW = "➜"
SYMBOL_STAR = "⭐"

# Tool Colors
TOOL_COLORS = {
    "subfinder": C_BRIGHT_CYAN,
    "httpx": C_BRIGHT_GREEN,
    "katana": C_BRIGHT_YELLOW,
    "gau": C_ORANGE,
    "gf": C_PURPLE,
    "kxss": C_PINK,
    "dalfox": C_BRIGHT_RED,
    "nuclei": C_BRIGHT_MAGENTA,
    "sqlmap": C_RED,
    "ffuf": C_BRIGHT_BLUE,
    "arjun": C_CYAN,
    "subjack": C_BRIGHT_CYAN,
    "default": C_BRIGHT_BLUE,
}


class BugxRunner:
    def __init__(self):
        self.tools = {}
        self.log_file_path = os.path.join(LOGS_DIR, "run.log")
        self.current_target = None
        self.current_mode = None
        self.scan_start_time = None
        self.findings = []

    def _log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = C_RESET
        symbol = ""

        if level == "WARNING":
            color = C_YELLOW
            symbol = SYMBOL_WARNING
        elif level == "ERROR":
            color = C_RED
            symbol = SYMBOL_ERROR
        elif level == "SUCCESS":
            color = C_GREEN
            symbol = SYMBOL_SUCCESS
        elif level == "INFO":
            color = C_CYAN
            symbol = SYMBOL_INFO

        log_message = f"{color}{symbol} [{timestamp}] [{level}]{C_RESET} {message}"
        print(log_message)
        with open(self.log_file_path, "a") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

    def _print_banner(self):
        banner = f"""
{C_BRIGHT_RED}██████╗ {C_BRIGHT_YELLOW}██╗   ██╗{C_BRIGHT_GREEN}██████╗ {C_BRIGHT_CYAN}    ██╗  ██╗
{C_BRIGHT_RED}██╔══██╗{C_BRIGHT_YELLOW}██║   ██║{C_BRIGHT_GREEN}██╔════╝ {C_BRIGHT_CYAN}    ╚██╗██╔╝
{C_BRIGHT_RED}██████╔╝{C_BRIGHT_YELLOW}██║   ██║{C_BRIGHT_GREEN}██║  ███╗{C_BRIGHT_CYAN}     ╚███╔╝
{C_BRIGHT_RED}██╔══██╗{C_BRIGHT_YELLOW}██║   ██║{C_BRIGHT_GREEN}██║   ██║{C_BRIGHT_CYAN}     ██╔██╗
{C_BRIGHT_RED}██████╔╝{C_BRIGHT_YELLOW}╚██████╔╝{C_BRIGHT_GREEN}╚██████╔╝{C_BRIGHT_CYAN}    ██╔╝ ██╗
{C_BRIGHT_RED}╚═════╝ {C_BRIGHT_YELLOW} ╚═════╝ {C_BRIGHT_GREEN} ╚═════╝ {C_BRIGHT_CYAN}    ╚═╝  ╚═╝{C_RESET}
        """
        print(banner)
        self._print_box(
            f"{SYMBOL_FIRE} BUG HUNTING AUTOMATION FRAMEWORK {SYMBOL_FIRE}\n"
            + f"{SYMBOL_STAR} Intelligent • Automated • Full Power {SYMBOL_STAR}",
            C_BRIGHT_CYAN,
            80,
        )
        print()

    def _print_box(self, text, color=C_CYAN, width=80):
        top_border = f"{color}╔{'═' * (width - 2)}╗{C_RESET}"
        bottom_border = f"{color}╚{'═' * (width - 2)}╝{C_RESET}"
        print(top_border)
        for line in text.split("\n"):
            padding = (width - 4 - len(line)) // 2
            padded_line = " " * padding + line + " " * (width - 4 - len(line) - padding)
            print(f"{color}║{C_RESET} {C_BOLD}{padded_line}{C_RESET} {color}║{C_RESET}")
        print(bottom_border)

    def _print_section_header(self, tool_name, description, target):
        tool_color = TOOL_COLORS.get(tool_name.lower(), TOOL_COLORS["default"])
        width = 100
        print(f"\n{tool_color}{'═' * width}{C_RESET}")
        print(
            f"{tool_color}║{C_RESET} {SYMBOL_TOOL} {C_BOLD}{tool_color}{tool_name.upper()}{C_RESET} {tool_color}║{C_RESET} {description}"
        )
        print(
            f"{tool_color}║{C_RESET} {SYMBOL_TARGET} Target: {C_BRIGHT_YELLOW}{target}{C_RESET}"
        )
        print(
            f"{tool_color}║{C_RESET} {SYMBOL_CLOCK} Started: {C_LIGHT_GRAY}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C_RESET}"
        )
        print(f"{tool_color}{'═' * width}{C_RESET}\n")

    def _print_section_footer(self, tool_name, status="success", duration=0.0):
        tool_color = TOOL_COLORS.get(tool_name.lower(), TOOL_COLORS["default"])
        width = 100
        if status == "success":
            symbol = SYMBOL_SUCCESS
            status_text = f"{C_BRIGHT_GREEN}COMPLETED{C_RESET}"
        elif status == "error":
            symbol = SYMBOL_ERROR
            status_text = f"{C_BRIGHT_RED}FAILED{C_RESET}"
        else:
            symbol = SYMBOL_WARNING
            status_text = f"{C_YELLOW}WARNING{C_RESET}"
        print(f"\n{tool_color}{'═' * width}{C_RESET}")
        print(
            f"{tool_color}║{C_RESET} {symbol} Status: {status_text} {tool_color}║{C_RESET} Duration: {C_CYAN}{duration:.2f}s{C_RESET}"
        )
        print(f"{tool_color}{'═' * width}{C_RESET}\n")

    def _discover_tools(self):
        path_dirs = os.environ.get("PATH", "").split(":")
        path_dirs.insert(0, BIN_DIR)
        for p in path_dirs:
            if not os.path.isdir(p):
                continue
            for item in os.listdir(p):
                path = os.path.join(p, item)
                if (
                    os.path.isfile(path)
                    and os.access(path, os.X_OK)
                    and item not in self.tools
                ):
                    self.tools[item] = path

    def _execute_command(self, tool_name, command, target, timeout=600):
        tool_color = TOOL_COLORS.get(tool_name.lower(), TOOL_COLORS["default"])
        self._print_section_header(tool_name, f"Executing {tool_name}", target)
        print(
            f"{SYMBOL_ROCKET} {C_BOLD}Command:{C_RESET} {C_LIGHT_GRAY}{command}{C_RESET}\n"
        )
        start_time = time.time()

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            def read_stream(stream, is_stderr=False):
                try:
                    for line in iter(stream.readline, ""):
                        if line:
                            line_stripped = line.rstrip()
                            if is_stderr:
                                print(
                                    f"{C_RED}{SYMBOL_WARNING} {line_stripped}{C_RESET}"
                                )
                            else:
                                print(
                                    f"{tool_color}{SYMBOL_ARROW} {line_stripped}{C_RESET}"
                                )
                except Exception:
                    pass

            stdout_thread = threading.Thread(
                target=read_stream, args=(process.stdout, False)
            )
            stderr_thread = threading.Thread(
                target=read_stream, args=(process.stderr, True)
            )
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            process.wait(timeout=timeout)
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            duration = time.time() - start_time
            if process.returncode == 0:
                self._print_section_footer(tool_name, "success", duration)
                return True
            else:
                self._print_section_footer(tool_name, "error", duration)
                return False
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self._print_section_footer(tool_name, "error", duration)
            self._log(f"{tool_name} timed out after {timeout} seconds.", level="ERROR")
            if process:
                process.kill()
                process.wait()
            return False
        except Exception as e:
            duration = time.time() - start_time
            self._print_section_footer(tool_name, "error", duration)
            self._log(f"Error executing {tool_name}: {e}", level="ERROR")
            return False

    def _clean_and_deduplicate_urls(self, input_file, output_file):
        if not os.path.exists(input_file):
            return False
        cleaned_urls = set()
        try:
            with open(input_file, "r") as f_in:
                for line in f_in:
                    url = line.strip()
                    if not url:
                        continue
                    url = re.sub(
                        r"\.(png|jpg|jpeg|gif|css|js|woff|ttf|eot|svg|ico)(\?.*)?$",
                        "",
                        url,
                        flags=re.IGNORECASE,
                    )
                    if not url:
                        continue
                    try:
                        parsed_url = urlparse(url)
                        query_params = parse_qs(parsed_url.query)
                        sorted_query = urlencode(
                            sorted(query_params.items()), doseq=True
                        )
                        cleaned_url = parsed_url._replace(
                            query=sorted_query, fragment=""
                        ).geturl()
                        cleaned_urls.add(cleaned_url)
                    except:
                        continue
            with open(output_file, "w") as f_out:
                for url in sorted(list(cleaned_urls)):
                    f_out.write(url + "\n")
            self._log(f"Cleaned {len(cleaned_urls)} unique URLs", level="SUCCESS")
            return True
        except Exception as e:
            self._log(f"Error cleaning URLs: {e}", level="ERROR")
            return False

    def _cleanup_tmp(self):
        self._log("Cleaning up temporary files...", level="INFO")
        if not os.path.exists(TMP_DIR):
            return
        for item in os.listdir(TMP_DIR):
            item_path = os.path.join(TMP_DIR, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                self._log(f"Error cleaning {item_path}: {e}", level="ERROR")
        self._log("Cleanup completed", level="SUCCESS")

    def _save_results(self, mode_name, target, findings):
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        result_dir = os.path.join(RESULTS_DIR, target_clean)
        os.makedirs(result_dir, exist_ok=True)
        output_file = os.path.join(result_dir, f"{mode_name.lower()}.json")
        result_data = {
            "target": target,
            "mode": mode_name,
            "scan_time": datetime.now().isoformat(),
            "duration": time.time() - self.scan_start_time
            if self.scan_start_time
            else 0,
            "findings_count": len(findings),
            "findings": findings,
        }
        try:
            with open(output_file, "w") as f:
                json.dump(result_data, f, indent=4)
            self._log(f"Results saved to {output_file}", level="SUCCESS")
            return output_file
        except Exception as e:
            self._log(f"Error saving results: {e}", level="ERROR")
            return None

    def _display_summary(self, mode_name, findings, output_file):
        print("\n")
        self._print_box(
            f"{SYMBOL_SCAN} SCAN SUMMARY {SYMBOL_SCAN}\n"
            + f"Mode: {mode_name}\n"
            + f"Target: {self.current_target}\n"
            + f"Findings: {len(findings)}\n"
            + f"Results: {output_file}",
            C_BRIGHT_MAGENTA,
            80,
        )
        print()

    def _run_recon(self, target, speed):
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        subdomains_file = os.path.join(TMP_DIR, f"{target_clean}_subdomains.txt")
        active_urls_file = os.path.join(TMP_DIR, f"{target_clean}_active_urls.txt")

        cmd = f"subfinder -d {target} -o {subdomains_file} -silent"
        self._execute_command("subfinder", cmd, target, timeout=600)

        if not os.path.exists(subdomains_file) or os.path.getsize(subdomains_file) == 0:
            self._log("No subdomains found, using main target", level="WARNING")
            with open(active_urls_file, "w") as f:
                f.write(f"http://{target}\nhttps://{target}\n")
        else:
            cmd = f"httpx -l {subdomains_file} -t {speed} -o {active_urls_file} -silent -mc 200,301,302,403"
            self._execute_command("httpx", cmd, target, timeout=600)

        return active_urls_file

    def _run_url_collection(self, active_urls_file, target, speed):
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        katana_file = os.path.join(TMP_DIR, f"{target_clean}_katana.txt")
        gau_file = os.path.join(TMP_DIR, f"{target_clean}_gau.txt")

        # Step 1: Run katana for crawling
        self._log("Running Katana crawler...", level="INFO")
        cmd = f"katana -list {active_urls_file} -c {speed} -o {katana_file} -silent -jc"
        self._execute_command("katana", cmd, target, timeout=900)

        # Step 2: Run GAU on katana results (GAU processes URLs from stdin)
        self._log("Running GAU on Katana results...", level="INFO")
        if os.path.exists(katana_file) and os.path.getsize(katana_file) > 0:
            cmd = f"cat {katana_file} | gau --threads {speed} --o {gau_file} 2>/dev/null || touch {gau_file}"
            self._execute_command("gau", cmd, target, timeout=600)
        else:
            self._log("Katana returned no results, skipping GAU", level="WARNING")
            open(gau_file, "w").close()

        # Count URLs from GAU
        gau_count = 0
        if os.path.exists(gau_file) and os.path.getsize(gau_file) > 0:
            with open(gau_file, "r") as f:
                gau_count = sum(1 for _ in f)
            self._log(f"GAU collected {gau_count} URLs from archives", level="INFO")
        else:
            self._log("GAU returned no results", level="WARNING")

        return gau_file

    def _run_xss_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting XSS Scanner for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []

        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)

        # Step 1: GF filters GAU results for XSS patterns
        self._log("GF filtering GAU results for XSS patterns...", level="INFO")
        gf_xss_file = os.path.join(TMP_DIR, f"{target_clean}_gf_xss.txt")
        cmd = f"cat {gau_file} | gf xss > {gf_xss_file} 2>/dev/null || touch {gf_xss_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_xss.txt")
        self._clean_and_deduplicate_urls(gf_xss_file, cleaned_file)

        # Step 2: Vulnerability scanners scan GF filtered results directly
        self._log("Scanning GF filtered URLs with Dalfox and Nuclei...", level="INFO")
        dalfox_result = os.path.join(TMP_DIR, f"{target_clean}_dalfox.json")
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_xss.json")

        cmd = f"dalfox file {gf_xss_file} -w {speed} -o {dalfox_result} --skip-mining-all --format json --silence 2>/dev/null || echo '[]' > {dalfox_result}"
        self._execute_command("dalfox", cmd, target, timeout=1800)

        cmd = f"nuclei -l {gf_xss_file} -tags xss -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)

        for result_file in [dalfox_result, nuclei_result]:
            if os.path.exists(result_file):
                try:
                    with open(result_file, "r") as f:
                        content = f.read().strip()
                        if content:
                            data = json.loads(content)
                            if isinstance(data, list):
                                findings.extend(data)
                            elif isinstance(data, dict):
                                findings.append(data)
                except Exception as e:
                    self._log(f"Error reading {result_file}: {e}", level="WARNING")

        return findings

    def _run_sqli_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting SQLi Scanner for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []

        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)

        # Step 1: GF filters GAU results for SQLi patterns
        self._log("GF filtering GAU results for SQLi patterns...", level="INFO")
        gf_sqli_file = os.path.join(TMP_DIR, f"{target_clean}_gf_sqli.txt")
        cmd = f"cat {gau_file} | gf sqli > {gf_sqli_file} 2>/dev/null || touch {gf_sqli_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_sqli.txt")
        self._clean_and_deduplicate_urls(gf_sqli_file, cleaned_file)

        scan_input = os.path.join(TMP_DIR, f"{target_clean}_sqli_limited.txt")
        cmd = f"head -20 {cleaned_file} > {scan_input}"
        subprocess.run(cmd, shell=True)

        # Step 2: Vulnerability scanners scan GF filtered results
        self._log(
            f"Scanning {scan_input} with Nuclei, SQLmap, and Arjun...", level="INFO"
        )
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_sqli.json")
        arjun_result = os.path.join(TMP_DIR, f"{target_clean}_arjun.txt")

        cmd = f"nuclei -l {scan_input} -tags sqli -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)

        cmd = f"sqlmap -m {scan_input} --batch --random-agent --level 1 --risk 1 --threads {speed} --output-dir {TMP_DIR}/sqlmap 2>/dev/null"
        self._execute_command("sqlmap", cmd, target, timeout=3600)

        cmd = f"arjun -i {scan_input} -oT {arjun_result} 2>/dev/null || touch {arjun_result}"
        self._execute_command("arjun", cmd, target, timeout=1800)

        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")

        sqlmap_dir = os.path.join(TMP_DIR, "sqlmap")
        if os.path.exists(sqlmap_dir):
            for root, dirs, files in os.walk(sqlmap_dir):
                for file in files:
                    if "vulnerable" in file.lower() or file.endswith(".log"):
                        findings.append(
                            {"tool": "sqlmap", "file": os.path.join(root, file)}
                        )

        return findings

    def _run_lfi_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting LFI Scanner for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []

        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)

        # Step 1: GF filters GAU results for LFI patterns
        self._log("GF filtering GAU results for LFI patterns...", level="INFO")
        gf_lfi_file = os.path.join(TMP_DIR, f"{target_clean}_gf_lfi.txt")
        cmd = f"cat {gau_file} | gf lfi > {gf_lfi_file} 2>/dev/null || touch {gf_lfi_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_lfi.txt")
        self._clean_and_deduplicate_urls(gf_lfi_file, cleaned_file)

        # Step 2: Vulnerability scanners scan GF filtered results
        self._log(f"Scanning GF filtered URLs with Nuclei and ffuf...", level="INFO")
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_lfi.json")
        ffuf_result = os.path.join(TMP_DIR, f"{target_clean}_ffuf_lfi.txt")

        cmd = f"nuclei -l {cleaned_file} -tags lfi,file -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)

        lfi_wordlist = os.path.join(WORDLISTS_DIR, "lfi.txt")
        if not os.path.exists(lfi_wordlist):
            os.makedirs(WORDLISTS_DIR, exist_ok=True)
            with open(lfi_wordlist, "w") as f:
                f.write(
                    "../../../../etc/passwd\n../../../etc/passwd\n../../etc/passwd\n"
                )

        cmd = f'head -10 {cleaned_file} | while read url; do ffuf -u "$url/FUZZ" -w {lfi_wordlist} -t {speed} -mc 200 -o {ffuf_result} 2>/dev/null; done'
        self._execute_command("ffuf", cmd, target, timeout=1800)

        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")

        return findings

    def _run_ssrf_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting SSRF Scanner for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []

        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)

        # Step 1: GF filters GAU results for SSRF patterns
        self._log("GF filtering GAU results for SSRF patterns...", level="INFO")
        gf_ssrf_file = os.path.join(TMP_DIR, f"{target_clean}_gf_ssrf.txt")
        cmd = f"cat {gau_file} | gf ssrf > {gf_ssrf_file} 2>/dev/null || touch {gf_ssrf_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_ssrf.txt")
        self._clean_and_deduplicate_urls(gf_ssrf_file, cleaned_file)

        # Step 2: Nuclei scans GF filtered results
        self._log(f"Scanning GF filtered URLs with Nuclei...", level="INFO")
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_ssrf.json")
        cmd = f"nuclei -l {cleaned_file} -tags ssrf -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)

        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")

        return findings

    def _run_rce_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting RCE Scanner for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []

        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)

        # Step 1: GF filters GAU results for RCE patterns
        self._log("GF filtering GAU results for RCE patterns...", level="INFO")
        gf_rce_file = os.path.join(TMP_DIR, f"{target_clean}_gf_rce.txt")
        cmd = f"cat {gau_file} | gf rce > {gf_rce_file} 2>/dev/null || touch {gf_rce_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_rce.txt")
        self._clean_and_deduplicate_urls(gf_rce_file, cleaned_file)

        # Step 2: Nuclei scans GF filtered results
        self._log(f"Scanning GF filtered URLs with Nuclei...", level="INFO")
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_rce.json")
        cmd = f"nuclei -l {cleaned_file} -tags rce,code -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)

        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")
        return findings

    def _run_subdomain_takeover_mode(self, target, speed):
        self._log(
            f"{SYMBOL_FIRE} Starting Subdomain Takeover Scanner for {target}",
            level="INFO",
        )
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []
        subdomains_file = os.path.join(TMP_DIR, f"{target_clean}_subdomains.txt")
        cmd = f"subfinder -d {target} -o {subdomains_file} -silent"
        self._execute_command("subfinder", cmd, target, timeout=600)
        subjack_result = os.path.join(TMP_DIR, f"{target_clean}_subjack.txt")
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_takeover.json")
        cmd = f"subjack -w {subdomains_file} -t {speed} -o {subjack_result} -ssl 2>/dev/null || touch {subjack_result}"
        self._execute_command("subjack", cmd, target, timeout=1800)
        cmd = f"nuclei -l {subdomains_file} -tags takeover -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)
        if os.path.exists(subjack_result):
            with open(subjack_result, "r") as f:
                for line in f:
                    if line.strip():
                        findings.append({"tool": "subjack", "finding": line.strip()})
        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")
        return findings

    def _run_info_disclosure_mode(self, target, speed):
        self._log(
            f"{SYMBOL_FIRE} Starting Information Disclosure Scanner for {target}",
            level="INFO",
        )
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []
        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_exposure.json")
        cmd = f"nuclei -l {gau_file} -tags exposure,config,disclosure -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)
        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")
        return findings

    def _run_auth_bypass_mode(self, target, speed):
        self._log(
            f"{SYMBOL_FIRE} Starting Auth Bypass Scanner for {target}", level="INFO"
        )
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []
        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_auth.json")
        cmd = f"nuclei -l {gau_file} -tags auth,login -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)
        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")
        return findings

    def _run_api_security_mode(self, target, speed):
        self._log(
            f"{SYMBOL_FIRE} Starting API Security Scanner for {target}", level="INFO"
        )
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []
        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_api.json")
        arjun_result = os.path.join(TMP_DIR, f"{target_clean}_arjun_api.txt")
        cmd = f"head -50 {gau_file} | arjun -i - -oT {arjun_result} 2>/dev/null || touch {arjun_result}"
        self._execute_command("arjun", cmd, target, timeout=1800)
        cmd = f"nuclei -l {gau_file} -tags api,graphql -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=1800)
        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")
        return findings

    def _run_full_scan_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting Full Scan for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []
        active_urls_file = self._run_recon(target, speed)
        gau_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_full.json")
        cmd = f"nuclei -l {gau_file} -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
        self._execute_command("nuclei", cmd, target, timeout=3600)
        if os.path.exists(nuclei_result):
            try:
                with open(nuclei_result, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if isinstance(data, list):
                            findings.extend(data)
            except Exception as e:
                self._log(f"Error reading nuclei results: {e}", level="WARNING")
        return findings

    def run_mode(self, mode_num, target, speed):
        self.current_target = target
        self.scan_start_time = time.time()
        mode_map = {
            1: ("XSS", self._run_xss_mode),
            2: ("SQLi", self._run_sqli_mode),
            3: ("LFI", self._run_lfi_mode),
            4: ("SSRF", self._run_ssrf_mode),
            5: ("RCE", self._run_rce_mode),
            6: ("Subdomain Takeover", self._run_subdomain_takeover_mode),
            7: ("Information Disclosure", self._run_info_disclosure_mode),
            8: ("Auth Bypass", self._run_auth_bypass_mode),
            9: ("API Security", self._run_api_security_mode),
            10: ("Full Scan", self._run_full_scan_mode),
        }
        if mode_num in mode_map:
            mode_name, mode_func = mode_map[mode_num]
            self.current_mode = mode_name
            findings = mode_func(target, speed)
            output_file = self._save_results(mode_name, target, findings)
            self._cleanup_tmp()
            self._display_summary(mode_name, findings, output_file)
            return findings
        return []

    def run_all_modes(self, target, speed):
        self._log(f"{SYMBOL_ROCKET} Starting RUN ALL MODES for {target}", level="INFO")
        all_findings = {}
        for mode_num in range(1, 11):
            self._log(f"\n{SYMBOL_STAR} Running Mode {mode_num}...", level="INFO")
            findings = self.run_mode(mode_num, target, speed)
            mode_name = [
                "XSS",
                "SQLi",
                "LFI",
                "SSRF",
                "RCE",
                "Subdomain Takeover",
                "Information Disclosure",
                "Auth Bypass",
                "API Security",
                "Full Scan",
            ][mode_num - 1]
            all_findings[mode_name] = findings
        total_findings = sum(len(f) for f in all_findings.values())
        print("\n")
        self._print_box(
            f"{SYMBOL_SCAN} RUN ALL SUMMARY {SYMBOL_SCAN}\n"
            + f"Target: {target}\n"
            + f"Total Findings: {total_findings}\n"
            + f"Modes Executed: 10",
            C_BRIGHT_MAGENTA,
            80,
        )
        return all_findings

    def main(self):
        self._discover_tools()
        self._print_banner()
        modes = {
            1: "XSS - Cross-Site Scripting",
            2: "SQLi - SQL Injection",
            3: "LFI - Local File Inclusion",
            4: "SSRF - Server-Side Request Forgery",
            5: "RCE - Remote Code Execution",
            6: "Subdomain Takeover",
            7: "Information Disclosure",
            8: "Auth Bypass",
            9: "API Security",
            10: "Full Scan - All Vulnerabilities",
            11: "Run All - Execute All Modes",
        }
        for num, desc in modes.items():
            print(f"{C_YELLOW}{num}. {desc}{C_RESET}")
        print(f"\n{C_BOLD}Select mode (1-11) or 'q' to quit:{C_RESET}")
        while True:
            try:
                selection = input(f"{C_GREEN}> {C_RESET}").strip()
                if selection.lower() == "q":
                    self._log("Exiting BUG.x", level="INFO")
                    return
                mode_num = int(selection)
                if mode_num not in modes:
                    self._log("Invalid mode number", level="WARNING")
                    continue
                break
            except ValueError:
                self._log("Please enter a number", level="WARNING")
        print()
        self._print_box(f"{SYMBOL_TARGET} TARGET SETUP", C_BRIGHT_CYAN, 80)
        target = input(
            f"{C_BOLD}Enter target domain (e.g., example.com): {C_RESET}"
        ).strip()
        if not target:
            self._log("Target cannot be empty", level="ERROR")
            return
        speed = input(
            f"{C_BOLD}Enter scan speed/threads (default: 50): {C_RESET}"
        ).strip()
        speed = int(speed) if speed.isdigit() else 50
        print()
        self._print_box(
            f"{SYMBOL_ROCKET} SCAN STARTING {SYMBOL_ROCKET}\n"
            + f"Target: {target}\n"
            + f"Mode: {modes[mode_num]}\n"
            + f"Speed: {speed} threads",
            C_BRIGHT_GREEN,
            80,
        )
        print()
        if mode_num == 11:
            self.run_all_modes(target, speed)
        else:
            self.run_mode(mode_num, target, speed)
        self._log(
            f"\n{SYMBOL_SUCCESS} Scan completed! Check results in {RESULTS_DIR}",
            level="SUCCESS",
        )


if __name__ == "__main__":
    runner = BugxRunner()
    runner.main()
