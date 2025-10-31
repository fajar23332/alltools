#!/usr/bin/env python3
import shutil

TOOLS = [
    "subfinder", "assetfinder", "amass", "gau", "waybackurls", "httpx",
    "naabu", "dnsx", "nuclei", "ffuf", "feroxbuster", "gobuster",
    "gospider", "httprobe", "chaos-client", "sqlmap", "masscan", "nmap",
    "whatweb", "wpscan", "eyewitness", "trufflehog", "subjack",
    "sublister", "shuffledns", "sensitivefinder", "goth", "aquatone",
    "dalfox", "gowitness", "xssfinder"
]

def check_tools():
    result = {}
    for tool in TOOLS:
        path = shutil.which(tool)
        result[tool] = bool(path)
    return result

if __name__ == "__main__":
    print(check_tools())
