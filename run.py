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
    "gitleaks": C_YELLOW,
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

    def _calculate_confidence(self, finding, tool_name):
        """Calculate confidence score for a finding"""
        confidence = 50  # Base confidence

        # Tool reliability scores
        tool_scores = {
            "nuclei": 85,
            "dalfox": 90,
            "sqlmap": 95,
            "subjack": 80,
            "ffuf": 70,
            "kxss": 75,
            "arjun": 65,
        }

        # Adjust based on tool
        if tool_name.lower() in tool_scores:
            confidence = tool_scores[tool_name.lower()]

        # Boost confidence if finding has specific indicators
        if isinstance(finding, dict):
            if finding.get("severity") in ["critical", "high"]:
                confidence += 10
            if finding.get("matcher-name"):
                confidence += 5
            if finding.get("curl-command") or finding.get("request"):
                confidence += 5

        return min(confidence, 99)  # Cap at 99%

    def _generate_validation_steps(self, finding, bug_type):
        """Generate step-by-step validation guide"""
        steps = []
        url = finding.get("url", finding.get("host", "N/A"))

        if bug_type.lower() == "xss":
            steps = [
                f"1. Buka URL: {url}",
                "2. Inject payload di parameter yang vulnerable",
                "3. Cek apakah payload ter-reflect di response",
                "4. Buka Developer Tools (F12) dan cek Console untuk alert/popup",
                "5. Screenshot sebagai bukti PoC",
            ]
        elif bug_type.lower() == "sqli":
            steps = [
                f"1. Buka URL: {url}",
                "2. Tambahkan payload: ' OR '1'='1",
                "3. Perhatikan SQL error message atau perubahan behavior",
                "4. Coba time-based: ' OR SLEEP(5)--",
                "5. Jika ada delay 5 detik, bug confirmed",
                "6. Screenshot error message sebagai proof",
            ]
        elif bug_type.lower() == "lfi":
            steps = [
                f"1. Buka URL: {url}",
                "2. Inject payload: ../../../../etc/passwd",
                "3. Cek response apakah ada file content",
                "4. Cari pattern: root:x:0:0",
                "5. Screenshot file content sebagai bukti",
            ]
        elif bug_type.lower() == "ssrf":
            steps = [
                f"1. Buka URL: {url}",
                "2. Setup Burp Collaborator atau interact.sh",
                "3. Inject payload dengan Collaborator URL",
                "4. Cek apakah ada callback/DNS request",
                "5. Screenshot callback log sebagai proof",
            ]
        elif "subdomain takeover" in bug_type.lower():
            steps = [
                f"1. Buka subdomain: {url}",
                "2. Cek CNAME record: nslookup atau dig",
                "3. Identify service provider (GitHub, AWS, etc)",
                "4. Claim subdomain di provider tersebut",
                "5. Upload PoC file untuk verifikasi",
            ]
        else:
            steps = [
                f"1. Buka URL: {url}",
                "2. Analisa finding details",
                "3. Attempt exploitation sesuai vulnerability type",
                "4. Dokumentasikan steps dan hasil",
                "5. Screenshot sebagai bukti",
            ]

        return steps

    def _generate_html_report(self, target, all_findings):
        """Generate beautiful HTML validation report"""
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        result_dir = os.path.join(RESULTS_DIR, target_clean)
        html_file = os.path.join(result_dir, "VALIDATION_REPORT.html")

        # Categorize findings by severity
        critical = []
        high = []
        medium = []
        low = []
        info = []

        bug_id = 1
        for mode_name, findings in all_findings.items():
            for finding in findings:
                severity = "info"
                if isinstance(finding, dict):
                    severity = finding.get(
                        "severity", finding.get("info", {}).get("severity", "info")
                    ).lower()

                # Add metadata
                enhanced_finding = {
                    "id": f"BUG-{bug_id:03d}",
                    "mode": mode_name,
                    "finding": finding,
                    "confidence": self._calculate_confidence(finding, mode_name),
                    "validation_steps": self._generate_validation_steps(
                        finding, mode_name
                    ),
                }

                if severity == "critical":
                    critical.append(enhanced_finding)
                elif severity == "high":
                    high.append(enhanced_finding)
                elif severity == "medium":
                    medium.append(enhanced_finding)
                elif severity == "low":
                    low.append(enhanced_finding)
                else:
                    info.append(enhanced_finding)

                bug_id += 1

        # Generate HTML
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BUG.x Validation Report - {target}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0a0e27; color: #fff; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px; border-radius: 10px; margin-bottom: 30px; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; font-size: 1.1em; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: #1a1f3a; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid; }}
        .summary-card.critical {{ border-color: #e74c3c; }}
        .summary-card.high {{ border-color: #e67e22; }}
        .summary-card.medium {{ border-color: #f39c12; }}
        .summary-card.low {{ border-color: #3498db; }}
        .summary-card.info {{ border-color: #95a5a6; }}
        .summary-card h2 {{ font-size: 2.5em; margin-bottom: 5px; }}
        .summary-card p {{ opacity: 0.8; text-transform: uppercase; font-size: 0.9em; }}
        .bug-section {{ margin-bottom: 30px; }}
        .bug-section h2 {{ font-size: 1.8em; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid; }}
        .bug-section.critical h2 {{ border-color: #e74c3c; color: #e74c3c; }}
        .bug-section.high h2 {{ border-color: #e67e22; color: #e67e22; }}
        .bug-section.medium h2 {{ border-color: #f39c12; color: #f39c12; }}
        .bug-section.low h2 {{ border-color: #3498db; color: #3498db; }}
        .bug-card {{ background: #1a1f3a; padding: 25px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid; }}
        .bug-card.critical {{ border-color: #e74c3c; }}
        .bug-card.high {{ border-color: #e67e22; }}
        .bug-card.medium {{ border-color: #f39c12; }}
        .bug-card.low {{ border-color: #3498db; }}
        .bug-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .bug-id {{ font-size: 1.2em; font-weight: bold; color: #667eea; }}
        .confidence {{ background: #27ae60; padding: 5px 15px; border-radius: 20px; font-size: 0.9em; }}
        .bug-info {{ margin-bottom: 15px; }}
        .bug-info p {{ margin-bottom: 8px; opacity: 0.9; }}
        .bug-info strong {{ color: #667eea; }}
        .validation-steps {{ background: #0f1229; padding: 15px; border-radius: 5px; margin-top: 15px; }}
        .validation-steps h4 {{ margin-bottom: 10px; color: #f39c12; }}
        .validation-steps ol {{ margin-left: 20px; }}
        .validation-steps li {{ margin-bottom: 8px; line-height: 1.6; }}
        .code {{ background: #0f1229; padding: 10px; border-radius: 5px; font-family: 'Courier New', monospace; font-size: 0.9em; overflow-x: auto; margin-top: 10px; }}
        .footer {{ text-align: center; margin-top: 50px; padding: 20px; opacity: 0.6; }}
        .checkbox {{ margin-right: 10px; transform: scale(1.5); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 BUG.x Validation Report</h1>
            <p>Target: {target} | Scan Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>

        <div class="summary">
            <div class="summary-card critical">
                <h2>{len(critical)}</h2>
                <p>Critical</p>
            </div>
            <div class="summary-card high">
                <h2>{len(high)}</h2>
                <p>High</p>
            </div>
            <div class="summary-card medium">
                <h2>{len(medium)}</h2>
                <p>Medium</p>
            </div>
            <div class="summary-card low">
                <h2>{len(low)}</h2>
                <p>Low</p>
            </div>
            <div class="summary-card info">
                <h2>{len(info)}</h2>
                <p>Info</p>
            </div>
        </div>
"""

        # Add findings by severity
        for severity_name, severity_list, color in [
            ("Critical", critical, "critical"),
            ("High", high, "high"),
            ("Medium", medium, "medium"),
            ("Low", low, "low"),
        ]:
            if severity_list:
                html_content += f'<div class="bug-section {color}"><h2>🎯 {severity_name} Severity Bugs ({len(severity_list)})</h2>'

                for bug in severity_list:
                    finding = bug["finding"]
                    url = finding.get(
                        "url", finding.get("host", finding.get("matched-at", "N/A"))
                    )
                    name = finding.get("info", {}).get(
                        "name",
                        finding.get("template-id", finding.get("tool", bug["mode"])),
                    )

                    html_content += f"""
        <div class="bug-card {color}">
            <div class="bug-header">
                <span class="bug-id">{bug["id"]}</span>
                <span class="confidence">Confidence: {bug["confidence"]}%</span>
            </div>
            <div class="bug-info">
                <p><strong>Type:</strong> {bug["mode"]}</p>
                <p><strong>Name:</strong> {name}</p>
                <p><strong>URL:</strong> <code>{url}</code></p>
                <p><input type="checkbox" class="checkbox"> <strong>Mark as Validated</strong></p>
            </div>
            <div class="validation-steps">
                <h4>📋 Validation Steps:</h4>
                <ol>
"""
                    for step in bug["validation_steps"]:
                        html_content += f"                    <li>{step}</li>\n"

                    html_content += """                </ol>
            </div>
        </div>
"""
                html_content += "</div>\n"

        html_content += """
        <div class="footer">
            <p>Generated by BUG.x Framework | Happy Bug Hunting! 🚀</p>
        </div>
    </div>
</body>
</html>
"""

        try:
            with open(html_file, "w") as f:
                f.write(html_content)
            return html_file
        except Exception as e:
            self._log(f"Error generating HTML report: {e}", level="ERROR")
            return None

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
        all_urls_file = os.path.join(TMP_DIR, f"{target_clean}_all_urls.txt")

        cmd = f"katana -list {active_urls_file} -c {speed} -o {katana_file} -silent -jc"
        self._execute_command("katana", cmd, target, timeout=900)

        cmd = f"cat {active_urls_file} | gau --o {gau_file} 2>/dev/null || touch {gau_file}"
        self._execute_command("gau", cmd, target, timeout=600)

        cmd = f"cat {katana_file} {gau_file} 2>/dev/null | sort -u > {all_urls_file}"
        subprocess.run(cmd, shell=True)

        return all_urls_file

    def _run_xss_mode(self, target, speed):
        self._log(f"{SYMBOL_FIRE} Starting XSS Scanner for {target}", level="INFO")
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        findings = []

        active_urls_file = self._run_recon(target, speed)
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)

        gf_xss_file = os.path.join(TMP_DIR, f"{target_clean}_gf_xss.txt")
        cmd = f"cat {all_urls_file} | gf xss > {gf_xss_file} 2>/dev/null || touch {gf_xss_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_xss.txt")
        self._clean_and_deduplicate_urls(gf_xss_file, cleaned_file)

        kxss_file = os.path.join(TMP_DIR, f"{target_clean}_kxss.txt")
        cmd = f"cat {cleaned_file} | kxss > {kxss_file} 2>/dev/null || cp {cleaned_file} {kxss_file}"
        self._execute_command("kxss", cmd, target, timeout=600)

        scan_input = (
            kxss_file
            if os.path.exists(kxss_file) and os.path.getsize(kxss_file) > 0
            else cleaned_file
        )

        dalfox_result = os.path.join(TMP_DIR, f"{target_clean}_dalfox.json")
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_xss.json")

        cmd = f"dalfox file {scan_input} -w {speed} -o {dalfox_result} --format json --silence 2>/dev/null || echo '[]' > {dalfox_result}"
        self._execute_command("dalfox", cmd, target, timeout=1800)

        cmd = f"nuclei -l {scan_input} -tags xss -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)

        gf_sqli_file = os.path.join(TMP_DIR, f"{target_clean}_gf_sqli.txt")
        cmd = f"cat {all_urls_file} | gf sqli > {gf_sqli_file} 2>/dev/null || touch {gf_sqli_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_sqli.txt")
        self._clean_and_deduplicate_urls(gf_sqli_file, cleaned_file)

        scan_input = os.path.join(TMP_DIR, f"{target_clean}_sqli_limited.txt")
        cmd = f"head -20 {cleaned_file} > {scan_input}"
        subprocess.run(cmd, shell=True)

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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)

        gf_lfi_file = os.path.join(TMP_DIR, f"{target_clean}_gf_lfi.txt")
        cmd = f"cat {all_urls_file} | gf lfi > {gf_lfi_file} 2>/dev/null || touch {gf_lfi_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_lfi.txt")
        self._clean_and_deduplicate_urls(gf_lfi_file, cleaned_file)

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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)

        gf_ssrf_file = os.path.join(TMP_DIR, f"{target_clean}_gf_ssrf.txt")
        cmd = f"cat {all_urls_file} | gf ssrf > {gf_ssrf_file} 2>/dev/null || touch {gf_ssrf_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_ssrf.txt")
        self._clean_and_deduplicate_urls(gf_ssrf_file, cleaned_file)

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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)

        gf_rce_file = os.path.join(TMP_DIR, f"{target_clean}_gf_rce.txt")
        cmd = f"cat {all_urls_file} | gf rce > {gf_rce_file} 2>/dev/null || touch {gf_rce_file}"
        self._execute_command("gf", cmd, target, timeout=300)

        cleaned_file = os.path.join(TMP_DIR, f"{target_clean}_cleaned_rce.txt")
        self._clean_and_deduplicate_urls(gf_rce_file, cleaned_file)

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
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_exposure.json")
        gitleaks_result = os.path.join(TMP_DIR, f"{target_clean}_gitleaks.json")
        cmd = f"nuclei -l {active_urls_file} -tags exposure,config,disclosure -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_auth.json")
        cmd = f"nuclei -l {all_urls_file} -tags auth,login -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_api.json")
        arjun_result = os.path.join(TMP_DIR, f"{target_clean}_arjun_api.txt")
        cmd = f"head -50 {all_urls_file} | arjun -i - -oT {arjun_result} 2>/dev/null || touch {arjun_result}"
        self._execute_command("arjun", cmd, target, timeout=1800)
        cmd = f"nuclei -l {all_urls_file} -tags api,graphql -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
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
        all_urls_file = self._run_url_collection(active_urls_file, target, speed)
        nuclei_result = os.path.join(TMP_DIR, f"{target_clean}_nuclei_full.json")
        cmd = f"nuclei -l {all_urls_file} -c {speed} -silent -je {nuclei_result} 2>/dev/null || echo '[]' > {nuclei_result}"
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
        self._log(
            f"{SYMBOL_ROCKET} Starting AUTOMATIC BUG HUNTING for {target}", level="INFO"
        )
        print(f"\n{C_BRIGHT_CYAN}{'=' * 80}{C_RESET}")
        print(
            f"{C_BOLD}{C_BRIGHT_MAGENTA}🎯 AUTO HUNT MODE - Find All Bugs Automatically!{C_RESET}"
        )
        print(f"{C_BRIGHT_CYAN}{'=' * 80}{C_RESET}\n")

        all_findings = {}
        mode_names = [
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
        ]

        for mode_num in range(1, 11):
            mode_name = mode_names[mode_num - 1]
            self._log(
                f"\n{SYMBOL_STAR} [{mode_num}/10] Scanning for {mode_name}...",
                level="INFO",
            )
            findings = self.run_mode(mode_num, target, speed)
            all_findings[mode_name] = findings
            print(
                f"{C_GREEN}{SYMBOL_SUCCESS} {mode_name}: {len(findings)} findings{C_RESET}"
            )

        total_findings = sum(len(f) for f in all_findings.values())

        # Generate HTML validation report
        print(f"\n{C_BRIGHT_YELLOW}📄 Generating validation report...{C_RESET}")
        html_report = self._generate_html_report(target, all_findings)

        # Save consolidated JSON
        target_clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        result_dir = os.path.join(RESULTS_DIR, target_clean)
        consolidated_json = os.path.join(result_dir, "ALL_FINDINGS.json")

        try:
            with open(consolidated_json, "w") as f:
                json.dump(
                    {
                        "target": target,
                        "scan_time": datetime.now().isoformat(),
                        "total_findings": total_findings,
                        "findings_by_mode": all_findings,
                    },
                    f,
                    indent=4,
                )
        except Exception as e:
            self._log(f"Error saving consolidated results: {e}", level="ERROR")

        # Display summary
        print("\n")
        print(f"{C_BRIGHT_CYAN}{'=' * 80}{C_RESET}")
        print(f"{C_BOLD}{C_BRIGHT_GREEN}✅ AUTOMATIC BUG HUNTING COMPLETED!{C_RESET}")
        print(f"{C_BRIGHT_CYAN}{'=' * 80}{C_RESET}\n")

        self._print_box(
            f"{SYMBOL_SCAN} SCAN SUMMARY {SYMBOL_SCAN}\n\n"
            + f"Target: {target}\n"
            + f"Total Findings: {total_findings}\n"
            + f"Modes Executed: 10/10\n\n"
            + f"{SYMBOL_STAR} Next Steps:\n"
            + f"1. Open HTML Report: {html_report}\n"
            + f"2. Follow validation steps for each bug\n"
            + f"3. Screenshot proof of concept\n"
            + f"4. Submit to bug bounty program!\n\n"
            + f"JSON Data: {consolidated_json}",
            C_BRIGHT_MAGENTA,
            80,
        )

        if html_report:
            print(
                f"\n{C_BRIGHT_GREEN}{SYMBOL_SUCCESS} HTML Validation Report: {C_BOLD}{html_report}{C_RESET}"
            )
            print(
                f"{C_BRIGHT_YELLOW}💡 Tip: Open the HTML file in your browser for a beautiful validation checklist!{C_RESET}\n"
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
            11: "🔥 AUTO HUNT - Find All Bugs Automatically! (Just Validate)",
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
