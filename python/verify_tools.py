import subprocess
import shutil
import sys

# safe probe with timeout and per-tool flags
SPECIAL_FLAGS = {
    # tools that choke on -V or --version; prefer -h or no-flag
    "naabu": ["-h"],
    "dnsx": ["-h"],
    "nuclei": ["-h"],
    "chaos-client": ["-h"],
    "httpx": ["-h"],
    "trufflehog": ["--help"],
    "gobuster": ["-h"],
    "ffuf": ["-h"],
    "whatweb": ["-h"],
    "feroxbuster": ["-h"],
    "eyewitness": ["--help"],
    "sublister": ["-h"],
    # fallback: try -h first for many that show help safely
}

def probe_tool(tool: str, to: int = 2) -> str:
    """
    Probe a tool safely with a Python-level timeout (seconds).
    Returns a one-line string or 'unknown'.
    """
    # if tool not in PATH quickly bail
    path = shutil.which(tool)
    if not path:
        return "missing"

    # candidate flags order
    flags = []
    if tool in SPECIAL_FLAGS:
        flags.extend(SPECIAL_FLAGS[tool])
    # then try common harmless flags
    flags.extend(["-h", "--help", "--version", "-v", "-V"])
    # finally try no flag
    flags.append("")

    for f in flags:
        try:
            cmd = [path] + ([f] if f else [])
            # run with timeout; capture output; don't allow interactive input
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=to)
            out = (proc.stdout or proc.stderr or "").strip()
            if out:
                # return first non-empty line truncated
                return out.splitlines()[0][:300]
        except subprocess.TimeoutExpired:
            # timeout — treat as unknown but continue trying other flags
            continue
        except Exception:
            # any other error (e.g. permission) -> continue
            continue

    # final fallback: run with a very small timeout
    try:
        proc = subprocess.run([path], capture_output=True, text=True, timeout=1)
        out = (proc.stdout or proc.stderr or "").strip()
        if out:
            return out.splitlines()[0][:300]
    except Exception:
        pass

    return "unknown"
