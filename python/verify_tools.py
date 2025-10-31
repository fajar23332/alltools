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
    v = "--verbose" in sys.argv or "-v" in sys.argv
    data = check_tools(verbose=v)
    if not v:
        # same behavior as original script: print dict
        print(data)
