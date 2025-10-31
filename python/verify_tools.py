#!/usr/bin/env python3
# python/verify_tools.py
# Safe tool presence checker — uses timeout when probing tools so it won't hang.

import shutil
import subprocess
import sys

TOOLS = [
    "subfinder", "assetfinder", "amass", "gau", "waybackurls", "httpx",
    "naabu", "dnsx", "nuclei", "ffuf", "feroxbuster", "gobuster", "gospider",
    "httprobe", "chaos-client", "sqlmap", "masscan", "nmap", "whatweb",
    "wpscan", "eyewitness", "trufflehog", "subjack", "sublister",
    "shuffledns", "aquatone", "dalfox", "gowitness", "xspear"
]

# seconds to wait for tool -h / --help / --version output
PROBE_TIMEOUT = 3


def probe_tool(tool: str) -> str:
    """
    Try to run tool with common help/version flags with a timeout.
    Returns first non-empty output line, or special tokens: 'timeout', 'error', 'no-output'
    """
    flags = [["-h"], ["--help"], ["--version"], ["-v"], ["-V"]]
    exe = shutil.which(tool) or tool
    for f in flags:
        try:
            completed = subprocess.run([exe] + f,
                                       capture_output=True, text=True,
                                       timeout=PROBE_TIMEOUT)
            out = (completed.stdout or completed.stderr or "").strip()
            if out:
                # return first non-empty line for quick summary
                return out.splitlines()[0].strip()
        except subprocess.TimeoutExpired:
            return "timeout"
        except FileNotFoundError:
            return "not-found"
        except Exception as e:
            # any other error - return a short marker
            return f"error:{type(e).__name__}"
    return "no-output"


def check_tools(verbose: bool = False) -> dict:
    """
    Return dict tool_name -> bool (True if installed).
    If verbose=True, also print quick probe summary (non-blocking).
    """
    result = {}
    for tool in TOOLS:
        installed = shutil.which(tool) is not None
        result[tool] = installed
        if verbose:
            if installed:
                info = probe_tool(tool)
                print(f"{tool:15} -> installed; probe: {info}")
            else:
                print(f"{tool:15} -> missing")
    return result


if __name__ == "__main__":
    import subprocess, time

    print("[*] Running tool inventory check...")

    data = check_tools()

    # probe tiap tool (biar gak hang lama)
    results = {}
    for tool, ok in data.items():
        if ok:
            try:
                # Timeout 2 detik per tool
                cmd = f"timeout 2s {tool} --version || timeout 2s {tool} -h || echo 'unknown'"
                out = subprocess.getoutput(cmd)
                first_line = out.splitlines()[0] if out.strip() else "unknown"
                results[tool] = f"installed; probe: {first_line}"
            except Exception as e:
                results[tool] = f"installed; probe failed: {e}"
        else:
            results[tool] = "missing"
        time.sleep(0.1)

    print()
    for k, v in results.items():
        status = "✔" if "installed" in v else "✖"
        print(f"  {status} {k.ljust(14)} — {v.split('probe:')[1].strip() if 'probe:' in v else v}")

    print("\n[*] Summary:")
    installed = [t for t, v in results.items() if "installed" in v]
    missing = [t for t, v in results.items() if "missing" in v]
    print(f"  Installed: {len(installed)} / {len(results)}")
    print(f"  Missing  : {', '.join(missing) if missing else 'None'}")

    # Simpan hasil ke file JSON
    import json
    with open("install_report.json", "w") as f:
        json.dump(results, f, indent=2)

    print("[*] DONE. Report saved to install_report.json")
