#!/usr/bin/env python3
# python/report.py — pretty report using verify_tools.check_tools()

from verify_tools import check_tools   # pastikan nama file verify_tools.py
import json
from datetime import datetime

def pretty_report(data: dict):
    print()
    print("=== Tools Report ===")
    print(f"Generated: {datetime.now().isoformat(sep=' ', timespec='seconds')}")
    ok = [k for k,v in data.items() if v]
    missing = [k for k,v in data.items() if not v]
    print(f"Found  : {len(ok)}")
    print(f"Missing: {len(missing)}")
    print()
    print("✅ Installed:")
    for n in sorted(ok):
        print(f"  - {n}")
    print()
    if missing:
        print("❌ Missing:")
        for n in sorted(missing):
            print(f"  - {n}")
    print()
    # also write JSON summary
    with open("install_report.json", "w") as fh:
        json.dump({"generated": datetime.now().isoformat(), "ok": ok, "missing": missing}, fh, indent=2)
    print("Wrote summary -> install_report.json")

if __name__ == "__main__":
    data = check_tools()   # fungsi verify_tools harus mengembalikan dict like {name: bool}
    pretty_report(data)
