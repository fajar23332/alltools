#!/usr/bin/env python3
# python/report.py — robust inventory + fast probes
from verify_tools import check_tools
from datetime import datetime
import subprocess, json, os, time

def probe_tool(tool, to=2):
    """Try --version, -V, -v, -h with timeout; return first non-empty line or 'unknown'."""
    flags = ["--version", "-V", "-v", "-h"]
    for f in flags:
        try:
            cmd = ["timeout", f"{to}s", tool, f]
            out = subprocess.run(cmd, capture_output=True, text=True)
            txt = (out.stdout or out.stderr).strip()
            if txt:
                return txt.splitlines()[0]
        except Exception:
            pass
    # last resort: command -v
    return "installed (no probe output)"

def pretty_report(results):
    os.system("clear" if os.name == "posix" else "cls")
    print("╔════════════════════════════════════╗")
    print("║        🧩  Tools Verification       ║")
    print("╚════════════════════════════════════╝\n")
    ok = [k for k,v in results.items() if v["found"]]
    missing = [k for k,v in results.items() if not v["found"]]
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"✅ Installed ({len(ok)}):")
    print("  " + ", ".join(sorted(ok)))
    print()
    print(f"❌ Missing ({len(missing)}):")
    print("  " + (", ".join(sorted(missing)) if missing else "None"))
    print()
    print("📋 Details (probe snippets):")
    for k in sorted(results.keys()):
        if results[k]["found"]:
            print(f"  ✔ {k.ljust(14)} — {results[k]['probe']}")
        else:
            print(f"  ✖ {k}")
    print()

if __name__ == "__main__":
    print("[*] Running tool inventory check...")
    detected = check_tools()
    results = {}
    for t, present in detected.items():
        if present:
            probe = probe_tool(t, to=2)
            results[t] = {"found": True, "probe": probe}
        else:
            results[t] = {"found": False, "probe": ""}
        # tiny sleep to avoid hammering terminal
        time.sleep(0.05)

    # write JSON summary
    with open("install_report.json", "w") as f:
        json.dump({k: v for k,v in results.items()}, f, indent=2)

    pretty_report(results)
    print("📁 Report saved to: install_report.json")
