#!/usr/bin/env python3
# python/report.py
from verify_tools import check_tools
from datetime import datetime
import json
import os

def pretty_report(data: dict):
    #os.system("clear" if os.name == "posix" else "cls")
    print("╔════════════════════════════════════╗")
    print("║        🧩  Tools Verification       ║")
    print("╚════════════════════════════════════╝\n")

    ok = [k for k,v in data.items() if v]
    missing = [k for k,v in data.items() if not v]

    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"✅ Installed ({len(ok)}):")
    print("  " + ", ".join(sorted(ok)))
    print()
    print(f"❌ Missing ({len(missing)}):")
    print("  " + ", ".join(sorted(missing)))
    print()

    # Simpan ke file JSON
    with open("install_report.json", "w") as f:
        json.dump({"ok": ok, "missing": missing, "timestamp": datetime.now().isoformat()}, f, indent=2)
    print("📁 Report saved to: install_report.json")

if __name__ == "__main__":
    data = check_tools()
    pretty_report(data)
