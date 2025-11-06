# 🐛 BUG.x - Bug Hunting Automation Framework

<div align="center">

```
██████╗ ██╗   ██╗██████╗     ██╗  ██╗
██╔══██╗██║   ██║██╔════╝     ╚██╗██╔╝
██████╔╝██║   ██║██║  ███╗     ╚███╔╝
██╔══██╗██║   ██║██║   ██║     ██╔██╗
██████╔╝╚██████╔╝╚██████╔╝    ██╔╝ ██╗
╚═════╝  ╚═════╝  ╚═════╝     ╚═╝  ╚═╝
```

**Intelligent • Automated • Full Power**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Bash](https://img.shields.io/badge/bash-5.0+-green.svg)](https://www.gnu.org/bash/)

</div>

---

## 📖 Overview

BUG.x adalah framework otomasi bug hunting yang cerdas dan terintegrasi. Framework ini dirancang untuk mengotomatisasi seluruh proses bug hunting mulai dari reconnaissance, scanning, hingga reporting dengan tampilan yang cantik dan user-friendly.

### ✨ Key Features

- 🎯 **11 Scanning Modes** - XSS, SQLi, LFI, SSRF, RCE, Subdomain Takeover, dan lebih
- 🚀 **Full Automation** - From reconnaissance to reporting
- 🎨 **Beautiful UI** - Color-coded live output per tool
- 🔄 **Cross-Validation** - Multiple tools scan same targets for accuracy
- 💾 **Auto-Save** - Results saved in JSON format
- 🧹 **Auto-Cleanup** - Temporary files cleaned automatically
- ⚡ **Optimized Pipelines** - Each mode has optimized tool chain

## 🎯 Scanning Modes

| # | Mode | Description | Tools Used |
|---|------|-------------|------------|
| 1 | **XSS** | Cross-Site Scripting | subfinder, httpx, katana, gau, gf, kxss, dalfox, nuclei |
| 2 | **SQLi** | SQL Injection | subfinder, httpx, katana, gau, gf, nuclei, sqlmap, arjun |
| 3 | **LFI** | Local File Inclusion | subfinder, httpx, katana, gau, gf, nuclei, ffuf |
| 4 | **SSRF** | Server-Side Request Forgery | subfinder, httpx, katana, gau, gf, nuclei |
| 5 | **RCE** | Remote Code Execution | subfinder, httpx, katana, gau, gf, nuclei |
| 6 | **Subdomain Takeover** | Find vulnerable subdomains | subfinder, subjack, nuclei |
| 7 | **Info Disclosure** | Detect exposed information | subfinder, httpx, nuclei |
| 8 | **Auth Bypass** | Authentication bypass | subfinder, httpx, katana, gau, nuclei |
| 9 | **API Security** | API security testing | subfinder, httpx, katana, gau, arjun, nuclei |
| 10 | **Full Scan** | All vulnerabilities | subfinder, httpx, katana, gau, nuclei (all templates) |
| 11 | **Run All** | Execute all modes sequentially | All modes 1-10 |

## 🚀 Quick Start

### Installation

```bash
# 1. Clone repository
git clone https://github.com/D0Lv-1N/BUGx.git
cd BUGx

# 2. Make scripts executable
chmod +x setup.sh activate.sh delete.sh

# 3. Run installer
./setup.sh
```

The installer will:
- ✅ Create necessary directories
- ✅ Install all required tools (34 tools)
- ✅ Capture help outputs
- ✅ Download wordlists
- ✅ Setup environment

### Usage

```bash
# 1. Activate environment
source activate.sh

# 2. Run BUG.x
python3 run.py

# 3. Select mode (1-11)
# 4. Enter target domain
# 5. Enter scan speed (default: 50)
# 6. Wait for results!
```

## 📋 Example Usage

### XSS Scan
```bash
$ python3 run.py
Select mode (1-11): 1
Enter target domain: testphp.vulnweb.com
Enter scan speed: 50
```

### Full Comprehensive Scan
```bash
$ python3 run.py
Select mode (1-11): 11
Enter target domain: example.com
Enter scan speed: 100
```

## 📊 Results

Results are automatically saved to:
```
~/BUGx/results/<target>/<mode>.json
```

Example:
```json
{
  "target": "example.com",
  "mode": "XSS",
  "scan_time": "2024-01-01T12:00:00",
  "duration": 1234.56,
  "findings_count": 5,
  "findings": [
    {...}
  ]
}
```

## 🛠️ Tools Used

### Core Tools (Must Have)
- **subfinder** - Subdomain discovery
- **httpx** - HTTP probing
- **katana** - Web crawler
- **gau** - URL harvesting from archives
- **nuclei** - Vulnerability scanner
- **gf** - Pattern matching
- **dalfox** - XSS scanner
- **sqlmap** - SQL injection scanner
- **ffuf** - Web fuzzer
- **arjun** - Parameter discovery
- **subjack** - Subdomain takeover checker

### Total: 34 Tools Installed
See [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) for complete list.

## 📁 Project Structure

```
~/BUGx/
├── setup.sh                 # Main installer
├── delete.sh               # Uninstaller
├── activate.sh             # Environment activator
├── run.py                  # Main scanner (764 lines)
├── laporan.txt             # Project documentation
├── QUICK_START.md          # Quick start guide
├── INSTALLATION_GUIDE.md   # Installation guide
├── README.md               # This file
├── .gitignore              # Git ignore rules
│
├── bin/                    # Tool symlinks (auto-created)
├── tools/                  # Build tools (auto-created)
├── logs/                   # Log files (auto-created)
├── help_output/            # Help outputs (auto-created)
├── tmp/                    # Temporary files (auto-created)
├── results/                # Scan results (auto-created)
└── wordlists/              # Wordlists (auto-created)
```

## 🔥 Pipeline Architecture

### XSS Mode Pipeline
```
subfinder → httpx → katana → gau (loop per domain) → gf xss 
  → URL cleaning → kxss → dalfox → nuclei
```

### SQLi Mode Pipeline
```
subfinder → httpx → katana → gau (loop per domain) → gf sqli 
  → URL cleaning → nuclei → sqlmap → arjun
```

### Key Design Principles
1. **Sequential Validation** - Scanner tools run one after another on SAME file
2. **Cross-Validation** - Multiple tools validate same targets
3. **Fallback Logic** - Pipeline continues even if one tool fails
4. **Auto-Cleanup** - Temporary files removed after scan

## ⚠️ Important Notes

### Legal Warning
⚠️ **Only scan targets you have permission to test!**

This tool is for educational and authorized security testing only. Unauthorized scanning is illegal and unethical.

### Performance Tips
- Higher speed = faster scan but more aggressive
- Use lower speed (20-50) for production targets
- Use higher speed (100-200) for CTF/test environments
- Mode 11 (Run All) takes longest time

### Best Practices
1. Always verify findings manually
2. Check logs for errors: `~/BUGx/logs/run.log`
3. Review JSON results for false positives
4. Use VPS for long-running scans
5. Respect rate limits

## 📚 Documentation

- [Quick Start Guide](QUICK_START.md) - Get started quickly
- [Installation Guide](INSTALLATION_GUIDE.md) - Detailed installation
- [laporan.txt](laporan.txt) - Project documentation (Indonesian)

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👤 Author

Created with ❤️ by Security Researcher

## 🙏 Acknowledgments

Special thanks to:
- ProjectDiscovery team for amazing tools
- All open-source security tool developers
- Bug bounty community

## 📞 Support

- 📖 Documentation: Check docs folder
- 🐛 Issues: GitHub Issues
- 💬 Discussions: GitHub Discussions

---

<div align="center">

**Happy Bug Hunting! 🐛🔫**

*Remember: With great power comes great responsibility*

</div>
