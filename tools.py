#!/usr/bin/env python3
"""
BUG-HUNTING v2 - interactive tools runner (single-tool by default; Custom mode for structured multi-run)
Author: ChatGPT for Dolvin
Usage:
  chmod +x tools.py
  ./tools.py
Requirements:
  - Python 3.8+
  - Tools you want to run must be installed and available in PATH (script detects and warns)
Notes:
  - Single-tool run => output file: <tool>-<target>.txt saved inside chosen output folder.
  - Custom run (multi-target or multi-tool) => output JSON files (structured).
  - Script previews final command(s) before execution and asks confirmation.
  - Auto-detects if target resolves (DNS). If target not resolvable, warns and aborts.
"""
import os
import sys
import subprocess
import socket
import shutil
import json
import time
from pathlib import Path

# -------------------------
# Config & Tool templates
# -------------------------
APP_NAME = "BUG-HUNTING v2"
VERSION = "1.0"
CLEAR_CMD = "cls" if os.name == "nt" else "clear"

# Terminal color helpers
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YEL = "\033[33m"
    BLUE = "\033[34m"
    MAG = "\033[35m"
    CYAN = "\033[36m"
    W = "\033[37m"

def clear():
    os.system(CLEAR_CMD)

def banner():
    clear()
    print(f"{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}║{C.RESET}  {C.BOLD}{APP_NAME}{C.RESET}  —  {C.DIM}Interactive single / custom tool runner{C.RESET}".ljust(55) + f"{C.CYAN}{C.BOLD}║{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}╚══════════════════════════════════════════════════════════╝{C.RESET}")
    print()

# Tools registry: key => (display_name, command_template, binary_check_name)
# command_template uses placeholders: {target} {speed} {out} {outfile} {infile}
# many commands chain outputs from previous steps; custom pipeline logic will wire them.
TOOLS = {
    "subfinder":    ("Subfinder",    "subfinder -d {target} -silent -o {outfile}", "subfinder"),
    "assetfinder":  ("Assetfinder",  "assetfinder {target} | tee {outfile}", "assetfinder"),
    "amass":        ("Amass",        "amass enum -d {target} -o {outfile}", "amass"),
    "gau":          ("gau",          "echo {target} | gau --o {outfile}", "gau"),
    "waybackurls":  ("WaybackURLs",  "echo {target} | waybackurls > {outfile}", "waybackurls"),
    "httpx":        ("httpx",        "httpx -l {infile} -silent -o {outfile} -json", "httpx"),
    "httpx-fast":   ("httpx (fast)", "httpx -l {infile} -silent -threads {speed} -o {outfile} -json", "httpx"),
    "naabu":        ("Naabu",        "echo {target} | naabu -silent -o {outfile}", "naabu"),
    "dnsx":         ("dnsx",         "dnsx -l {infile} -a -resp -o {outfile}", "dnsx"),
    "nuclei":       ("Nuclei",       "nuclei -l {infile} -o {outfile} -json -severity critical,high,medium", "nuclei"),
    "ffuf":         ("ffuf",         "ffuf -u {target}/FUZZ -w {wordlist} -o {outfile} -of json -t {speed}", "ffuf"),
    "gobuster":     ("Gobuster",     "gobuster dir -u {target} -w {wordlist} -o {outfile} -q", "gobuster"),
    "feroxbuster":  ("Feroxbuster",  "feroxbuster -u {target} -w {wordlist} -o {outfile} --format json", "feroxbuster"),
    "dirsearch":    ("Dirsearch",    "python3 dirsearch/dirsearch.py -u {target} -e * -o {outfile}", "dirsearch"),
    "gospider":     ("Gospider",     "gospider -s https://{target} -o {outfile}", "gospider"),
    "xray":         ("XRay",         "xray webscan --basic {target} --json-output {outfile}", "xray"),  # placeholder; user must have xray
    "sqlmap":       ("Sqlmap",       "sqlmap -u {target} --batch --output-dir={outdir} > {outfile}", "sqlmap"),
    "dalfox":       ("Dalfox",       "dalfox file {infile} -o {outfile} -w {wordlist}", "dalfox"),
    "masscan":      ("Masscan",      "masscan {target} -p1-65535 --rate {speed} -oJ {outfile}", "masscan"),
    "nmap":         ("Nmap",         "nmap -Pn -sV -oJ {outfile} {target}", "nmap"),
    "whatweb":      ("WhatWeb",      "whatweb -v {target} -a 3 -o {outfile}", "whatweb"),
    "wpscan":       ("WPScan",       "wpscan --url {target} -o {outfile}", "wpscan"),
    "aquatone":     ("Aquatone",     "cat {infile} | aquatone -out {outdir} && echo 'html in {outdir}' > {outfile}", "aquatone"),
    "gowitness":    ("GoWitness",    "gowitness file -f {infile} --output {outdir} && echo done > {outfile}", "gowitness"),
    "eyewitness":   ("EyeWitness",   "python3 EyeWitness/EyeWitness.py -f {infile} -d {outdir} && echo done > {outfile}", "EyeWitness"),
    "trufflehog":   ("TruffleHog",   "trufflehog --json {target} > {outfile}", "trufflehog"),
    "subjack":      ("Subjack",      "subjack -w {infile} -t {speed} -o {outfile} -ssl", "subjack"),
    "httprobe":     ("httprobe",     "cat {infile} | httprobe -c {speed} > {outfile}", "httprobe"),
    "sublister":    ("Sublist3r",    "subfinder -d {target} -o {outfile}", "subfinder"),
    "shuffledns":   ("Shuffledns",   "shuffledns -d {target} -r resolvers.txt -o {outfile}", "shuffledns"),
    "sensitive":    ("SensitiveFind", "gau --subs {target} | grep -iE 'password|secret|token' > {outfile}", "gau"),
    # add more if needed...
}

# Wordlist default (can be changed)
DEFAULT_WORDLIST = "/usr/share/wordlists/dirb/common.txt"

# Structured pipeline groups (discovery -> probe -> fuzz -> scan)
PIPELINES = {
    "discovery": ["subfinder", "assetfinder", "amass"],
    "passive": ["gau", "waybackurls", "gospider"],
    "probe": ["httpx", "httprobe", "naabu", "dnsx"],
    "fuzz": ["ffuf", "gobuster", "feroxbuster", "dirsearch"],
    "vuln_scan": ["nuclei", "xray", "sqlmap", "dalfox"],
    "post": ["aquatone", "gowitness", "eyewitness"]
}

# Tools that MUST consume a file input (list of hosts/urls) for -l or similar
TOOLS_USE_INFILE = {"httpx", "dnsx", "nuclei", "httprobe", "gowitness", "aquatone", "dalfox"}

# -------------------------
# Helpers
# -------------------------
def check_binary(binname):
    """Return True if binary available in PATH or in current directory bins."""
    return shutil.which(binname) is not None

def resolve_target(target):
    """Return True if DNS resolves or target is reachable via socket (quick)."""
    try:
        # try hostname resolution
        socket.gethostbyname(target)
        return True
    except Exception:
        return False

def safe_mkdir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def ask(prompt, default=None):
    if default is not None:
        r = input(f"{prompt} [default: {default}]: ").strip()
        return r if r else default
    return input(f"{prompt}: ").strip()

def run_shell(cmd, env=None):
    """Run shell command and stream output; return rc."""
    print(f"{C.DIM}\n>>> {cmd}{C.RESET}\n")
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
    try:
        while True:
            line = p.stdout.readline()
            if not line and p.poll() is not None:
                break
            if line:
                print(line, end="")
        return p.returncode
    except KeyboardInterrupt:
        p.kill()
        return -1

def preview_and_confirm(commands):
    print(f"\n{C.BOLD}Preview of commands to run:{C.RESET}")
    for i, c in enumerate(commands, 1):
        print(f"  {i}. {C.YELLOW}{c}{C.RESET}")
    ans = ask("Preview OK? run commands? (y/n)", "y").lower()
    return ans in ("y", "yes")

# -------------------------
# Workflow primitives
# -------------------------
def build_single_command(tool_key, target, speed, outdir, infile=None, wordlist=None, mode_flags="default"):
    """Return command string for single tool and single target. Uses templates above."""
    tpl = TOOLS.get(tool_key)
    if not tpl:
        raise ValueError("Unknown tool")
    _, template, bincheck = tpl
    if wordlist is None:
        wordlist = DEFAULT_WORDLIST
    outfile_name = f"{tool_key}-{target}.txt"  # single target naming as requested
    outfile = os.path.join(outdir, outfile_name)
    # prepare infile path if present
    if infile is None:
        # for some tools infile should default to previously produced files (like subfinder)
        infile = os.path.join(outdir, f"subfinder-{target}.txt")
    filled = template.format(
        target=target,
        speed=speed,
        out=outdir,
        outdir=outdir,
        outfile=outfile,
        infile=infile,
        wordlist=wordlist
    )
    # adjust flags for "fullpower"
    if mode_flags == "fullpower":
        # naive mapping: add threads/high rate for certain tools
        if tool_key in {"ffuf", "feroxbuster", "gobuster"}:
            filled = filled.replace("-t {speed}", f"-t {speed}")
            filled = filled.replace("{speed}", str(int(speed) * 2))
        if tool_key in {"naabu", "masscan"}:
            filled = filled.replace("{speed}", str(int(speed) * 200))
        if tool_key in {"httpx"}:
            filled = filled.replace("-threads {speed}", f"-threads {speed}")
    return filled, outfile

# structured custom-run engine
def run_pipeline_ordered(tools_list, target, speed, base_out, wordlist, mode_flags):
    """
    Run tools in a structured order. Tools_list is a list of tool keys.
    The engine will:
      - For each tool, check if it requires an infile; pass prior outputs as infile when logical.
      - Save outputs with naming rules.
      - Ask to continue between major groups if user wants.
    """
    # mapping last useful file produced to be used as infile
    last_host_file = None
    for tool_key in tools_list:
        clear()
        banner()
        display_name = TOOLS[tool_key][0]
        print(f"{C.BOLD}Running ->{C.RESET} {display_name} ({tool_key})\nTarget: {target}\nOutput folder: {base_out}")
        # derive infile
        infile = last_host_file if (tool_key in TOOLS_USE_INFILE) else None
        cmd, outfile = build_single_command(tool_key, target, speed, base_out, infile=infile, wordlist=wordlist, mode_flags=mode_flags)
        # check binary presence
        bincheck = TOOLS[tool_key][2]
        if not check_binary(bincheck):
            print(f"{C.RED}Tool {display_name} ({bincheck}) not found in PATH. Skipping.{C.RESET}")
            # record fail file
            print(f"Recommendation: install `{bincheck}` or skip this tool.")
            continue
        # preview & exec
        if preview_and_confirm([cmd]):
            rc = run_shell(cmd)
            if rc == 0:
                print(f"\n{C.GREEN}{display_name} finished successfully.{C.RESET}")
            else:
                print(f"\n{C.RED}{display_name} returned rc={rc}{C.RESET}")
        else:
            print(f"{C.YEL}Skipped {display_name} by user.{C.RESET}")
        # update last_host_file heuristics: if tool produced a hosts list, set it
        # Known producers: subfinder -> subfinder-<target>.txt, amass -> amass-<target>.txt, gau/waybackurls produce url lists
        potential_files = [
            os.path.join(base_out, f"subfinder-{target}.txt"),
            os.path.join(base_out, f"amass-{target}.txt"),
            os.path.join(base_out, f"assetfinder-{target}.txt"),
            os.path.join(base_out, f"gau-{target}.txt"),
            os.path.join(base_out, f"waybackurls-{target}.txt"),
            os.path.join(base_out, f"httpx-{target}.txt"),
        ]
        for pf in potential_files:
            if os.path.exists(pf):
                last_host_file = pf
                break
        time.sleep(1)
    print(f"\n{C.CYAN}Pipeline complete.{C.RESET}")

# -------------------------
# Main interactive flow
# -------------------------
def main_menu():
    while True:
        banner()
        print(f"{C.BOLD}Main Menu{C.RESET}")
        print("Choose a tool to run (single-tool), or choose Custom Mode for structured multi-tool execution.")
        print()
        # nice columns
        keys = list(TOOLS.keys())
        # print as numbered list with short names
        i = 1
        for k, v in TOOLS.items():
            print(f" {C.GREEN}{str(i).rjust(2)}{C.RESET}. {v[0]:20} ({k})", end="")
            if i % 3 == 0:
                print()
            i += 1
        print()
        print(f"\n {C.MAG}99{C.RESET}. Custom Mode (structured pipeline)")
        print(f" {C.RED}0{C.RESET}. Exit")
        choice = ask("Pick option number (or tool key like 'subfinder')", "")
        if choice.strip() == "":
            continue
        if choice == "0":
            print("bye.")
            sys.exit(0)
        if choice == "99" or choice.lower() in ("custom", "c"):
            custom_mode_interactive()
            input("\nPress Enter to return to main menu...")
            continue
        # allow numeric selection or key name
        tool_key = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(TOOLS):
                tool_key = list(TOOLS.keys())[idx]
        else:
            if choice in TOOLS:
                tool_key = choice
            else:
                # allow case-insensitive match by name
                for k, v in TOOLS.items():
                    if v[0].lower().startswith(choice.lower()):
                        tool_key = k
                        break
        if not tool_key:
            print(f"{C.RED}Invalid choice. Try again.{C.RESET}")
            time.sleep(1)
            continue
        # SINGLE TOOL FLOW
        single_tool_flow(tool_key)

def single_tool_flow(tool_key):
    clear(); banner()
    display = TOOLS[tool_key][0]
    print(f"{C.BOLD}SINGLE TOOL MODE{C.RESET} — {display}\n")
    target = ask("Input target (Example: example.com)", "example.com")
    # auto-detect target
    if not resolve_target(target):
        print(f"{C.RED}Target {target} did not resolve via DNS. Aborting.{C.RESET}")
        return
    speed = ask("Input speed (threads/rate, numeric) (Example: 50)", "50")
    print("\nFlag mode:")
    print(" 1) Full Power flags (aggressive) — 'fullpower'")
    print(" 2) Standard flags (default) — 'default'")
    fm = ask("Choose flags mode (1/2)", "2")
    flags_mode = "fullpower" if fm.strip() == "1" else "default"
    outfolder = ask("Output folder name (Example: results)", "results")
    safe_mkdir(outfolder)
    # generate single command preview
    cmd, outfile = build_single_command(tool_key, target, speed, outfolder, infile=None, wordlist=DEFAULT_WORDLIST, mode_flags=flags_mode)
    print(f"\nPreview (single-target => output will be saved as {outfile}):")
    print(f"{C.YELLOW}{cmd}{C.RESET}\n")
    ok = ask("Run this command? (y/n)", "y")
    if ok.lower() not in ("y", "yes"):
        print("Aborted by user.")
        return
    # ensure tool present
    bincheck = TOOLS[tool_key][2]
    if not check_binary(bincheck):
        print(f"{C.RED}Tool {display} ({bincheck}) not found in PATH. Aborting.{C.RESET}")
        print(f"Recommendation: install `{bincheck}` then re-run script.")
        return
    rc = run_shell(cmd)
    if rc == 0:
        # ensure file naming: for single target must be .txt (already done)
        print(f"\n{C.GREEN}Success — output at {outfile}{C.RESET}")
    else:
        print(f"\n{C.RED}Command exited with code {rc}. Check output above.{C.RESET}")

def custom_mode_interactive():
    clear(); banner()
    print(f"{C.BOLD}CUSTOM MODE - Structured Multi-Tool{C.RESET}")
    print("You will pick a pipeline (discovery / passive / probe / fuzz / vuln_scan / post) or custom list.")
    print("This will run tools sequentially in a structured order. Tools that require file inputs will use previous results when possible.")
    print()
    print("Pipelines available:")
    for p in PIPELINES:
        print(f" - {C.GREEN}{p}{C.RESET}: {', '.join(PIPELINES[p])}")
    print()
    pipe = ask("Select pipeline name (or type 'custom' to pick tools manually)", "discovery")
    selected_tools = []
    if pipe.lower() == "custom":
        print("Enter tool keys separated by commas (example: subfinder,httpx,nuclei)")
        print("Available tools:", ", ".join(TOOLS.keys()))
        raw = ask("Tools:", "subfinder,httpx,nuclei")
        selected_tools = [t.strip() for t in raw.split(",") if t.strip() in TOOLS]
        if not selected_tools:
            print("No valid tools selected. Abort.")
            return
    else:
        if pipe not in PIPELINES:
            print("Unknown pipeline. Abort.")
            return
        selected_tools = PIPELINES[pipe]
    # target(s)
    mode = ask("Single target or targets file? (type 'single' or 'file')", "single")
    if mode == "single":
        target = ask("Input target (Example: example.com)", "example.com")
        if not resolve_target(target):
            print(f"{C.RED}Target {target} did not resolve. Abort.{C.RESET}")
            return
    else:
        tf = ask("Path to targets file (one host per line). Example: ./targets.txt", "targets.txt")
        if not os.path.exists(tf):
            print(f"{C.RED}Targets file not found: {tf}{C.RESET}")
            return
        target = None
    speed = ask("Input speed (numeric) (Example: 50)", "50")
    print("\nFlag mode: 1) Full Power  2) Default")
    fm = ask("Choose flags mode (1/2)", "2")
    flags_mode = "fullpower" if fm.strip() == "1" else "default"
    outfolder = ask("Output folder name (Example: results_custom)", "results_custom")
    safe_mkdir(outfolder)
    print("\nPreview structured run:")
    # Build commands list (with infile wiring)
    commands = []
    last_file = None
    for tkey in selected_tools:
        tpl, _ = TOOLS[tkey], None
        cmd, outfile = build_single_command(tkey, target if target else "{target}", speed, outfolder, infile=last_file, wordlist=DEFAULT_WORDLIST, mode_flags=flags_mode)
        # If multi targets file mode, replace placeholders differently
        if mode != "single":
            # tools that accept -l or file input will be run with the targets file
            if tkey in TOOLS_USE_INFILE:
                cmd = cmd.replace("{infile}", tf).replace("{target}", "").replace("  ", " ")
                outfile = os.path.join(outfolder, f"{tkey}-targets.json")
            else:
                cmd = cmd.replace("{target}", f" -iL {tf} ")
                outfile = os.path.join(outfolder, f"{tkey}-targets.json")
        commands.append((tkey, cmd, outfile))
        # heuristics: next tools that need infile will use current outfile if sensible
        if os.path.splitext(outfile)[1] in {".txt", ".json"}:
            last_file = outfile
    # Show preview
    for i, (tkey, cmd, outfile) in enumerate(commands, 1):
        print(f" {i}. {TOOLS[tkey][0]} -> {C.YELLOW}{outfile}{C.RESET}")
        print(f"    {C.DIM}{cmd}{C.RESET}")
    ok = ask("Run this structured pipeline? (y/n)", "y")
    if ok.lower() not in ("y", "yes"):
        print("Cancelled.")
        return
    # Execute sequentially; for each tool, check binary then run.
    for tkey, cmd, outfile in commands:
        display = TOOLS[tkey][0]
        clear(); banner()
        print(f"{C.BOLD}Running {display}{C.RESET}")
        # check binary
        bincheck = TOOLS[tkey][2]
        if not check_binary(bincheck):
            print(f"{C.RED}Binary {bincheck} not found. Options: (s)kip / (a)bort{C.RESET}")
            choice = ask("Choose (s/a)", "s")
            if choice.lower().startswith("a"):
                print("Aborting pipeline.")
                return
            else:
                print(f"Skipping {display}.")
                time.sleep(1)
                continue
        # if single mode, replace {target}
        if mode == "single":
            cmd = cmd.replace("{target}", target)
        # run
        print(f"Command:\n{C.YELLOW}{cmd}{C.RESET}\nOutput: {outfile}")
        run_ok = preview_and_confirm([cmd])
        if not run_ok:
            print("User skipped execution of this step.")
            continue
        rc = run_shell(cmd)
        if rc != 0:
            print(f"{C.RED}Tool {display} returned exit {rc}.{C.RESET}")
            cont = ask("Continue pipeline? (y to continue / n to abort)", "y")
            if cont.lower() not in ("y", "yes"):
                print("Aborting pipeline.")
                return
        else:
            print(f"{C.GREEN}{display} finished, output -> {outfile}{C.RESET}")
        time.sleep(1)
    print(f"\n{C.CYAN}Custom pipeline complete. Outputs in folder: {outfolder}{C.RESET}")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nInterrupted — bye.")
        sys.exit(0)
