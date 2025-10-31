#!/usr/bin/env python3
# python/verify_tools.py
import shutil

TOOLS = [
    "subfinder", "assetfinder", "amass", "gau", "waybackurls", "httpx",
    "naabu", "dnsx", "nuclei", "ffuf", "feroxbuster", "gobuster", "gospider",
    "httprobe", "chaos-client", "sqlmap", "masscan", "nmap", "whatweb",
    "wpscan", "eyewitness", "trufflehog", "subjack", "sublister",
    "shuffledns", "sensitivefinder", "goth", "aquatone", "dalfox", "gowitness",
    "xssfinder"
]

def check_tools():
    """Return dict of tool_name -> bool (True if installed)"""
    result = {}
    for tool in TOOLS:
        result[tool] = shutil.which(tool) is not None
    return result

if __name__ == "__main__":
    print(check_tools())






