#!/usr/bin/env python3
import shutil, argparse

TOOLS = [
 "subfinder","assetfinder","amass","gau","waybackurls","httpx",
 "naabu","dnsx","nuclei","ffuf","feroxbuster","gobuster","gospider",
 "httprobe","chaos-client","sqlmap","masscan","nmap","whatweb",
 "wpscan","eyewitness","trufflehog","subjack","sublister",
 "shuffledns","aquatone","dalfox","gowitness","xspear"
]

def check_tools():
    return {t: shutil.which(t) is not None for t in TOOLS}

if __name__ == "__main__":
    import json
    print(json.dumps(check_tools(), indent=2))
