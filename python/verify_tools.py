#!/usr/bin/env python3
import shutil, argparse

TOOLS = [
 "subfinder","assetfinder","amass","gau","waybackurls","httpx",
 "naabu","dnsx","nuclei","ffuf","feroxbuster","gobuster","gospider",
 "httprobe","chaos-client","sqlmap","masscan","nmap","whatweb",
 "wpscan","eyewitness","trufflehog","subjack","sublister",
 "shuffledns","aquatone","dalfox","gowitness","xspear"
]


# paste this near the top of python/verify_tools.py (after imports)
import subprocess

def probe_tool(tool: str, to: int = 2) -> str:
    """
    Try probing a tool safely with a timeout to avoid hangs.
    Returns a short one-line probe string or 'unknown'.
    'to' is timeout in seconds.
    """
    flags = ["--version", "-version", "-v", "-V", "version", "-h", "--help", "help"]
    for f in flags:
        try:
            # use timeout to avoid hanging tools
            proc = subprocess.run(
                ["timeout", f"{to}s", tool, f],
                capture_output=True, text=True
            )
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                return out.splitlines()[0][:200]
        except Exception:
            continue

    # fallback: try running tool alone for a short time
    try:
        proc = subprocess.run(["timeout", f"{to}s", tool], capture_output=True, text=True)
        out = (proc.stdout or proc.stderr or "").strip()
        if out:
            return out.splitlines()[0][:200]
    except Exception:
        pass

    return "unknown"

def check_tools():
    return {t: shutil.which(t) is not None for t in TOOLS}

if __name__ == "__main__":
    import json
    print(json.dumps(check_tools(), indent=2))
