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

## 🔥 FITUR UTAMA: AUTO HUNT MODE

**Sekali input URL → Langsung dapat list bug → Tinggal validasi!**

Mode AUTO HUNT (Mode 11) adalah fitur revolusioner yang membuat bug hunting menjadi sangat mudah:

1. ✅ **Input target sekali** - Hanya masukkan domain
2. ✅ **Auto scan semua vulnerability** - 10 mode berjalan otomatis
3. ✅ **Confidence scoring** - Setiap bug punya confidence %
4. ✅ **Validation guide** - Step-by-step cara validate tiap bug
5. ✅ **Beautiful HTML report** - Interactive checklist dengan severity coloring
6. ✅ **User hanya validate & submit** - No need deep technical knowledge!

### 💰 Real Impact:
```
Input: example.com
Wait: 30-60 menit
Output: HTML Report dengan 15+ potential bugs
Your Job: Buka report → Follow steps → Validate → Submit → Get paid! 💵
```

### ✨ All Features

- 🎯 **11 Scanning Modes** - XSS, SQLi, LFI, SSRF, RCE, Subdomain Takeover, dan lebih
- 🚀 **Full Automation** - From reconnaissance to reporting
- 🎨 **Beautiful UI** - Color-coded live output per tool
- 🔄 **Cross-Validation** - Multiple tools scan same targets for accuracy
- 💾 **Auto-Save** - Results saved in JSON format
- 📄 **HTML Validation Report** - Interactive bug validation checklist
- 🎯 **Confidence Scoring** - Prioritize high-confidence bugs
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
| 11 | **🔥 AUTO HUNT** | **One-click bug hunting!** | All modes 1-10 + HTML report + validation guide |

## 🚀 Quick Start

### Installation

```bash
# 1. Clone repository
git clone https://github.com/D0Lv-1N/BUGx.git
cd BUGx

# 2. Make scripts executable
chmod +x setup.sh

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

#### 🔥 RECOMMENDED: AUTO HUNT Mode (Easiest!)

```bash
# 1. Activate environment
source activate.sh

# 2. Run BUG.x
python3 run.py

# 3. Select mode: 11 (AUTO HUNT)
# 4. Enter target domain: example.com
# 5. Enter scan speed: 50 (or press Enter for default)
# 6. Wait 30-60 minutes
# 7. Open HTML report and start validating bugs!

# Result location:
# HTML: ~/BUGx/results/example.com/VALIDATION_REPORT.html
# JSON: ~/BUGx/results/example.com/ALL_FINDINGS.json
```

#### Single Mode Usage

```bash
# For testing specific vulnerability
python3 run.py
# Select mode (1-10)
# Enter target domain
# Enter scan speed
```

## 📋 Example Usage

### 🔥 AUTO HUNT Mode (RECOMMENDED)
```bash
$ python3 run.py
Select mode (1-11): 11
Enter target domain: example.com
Enter scan speed: 50

# Output akan tampil:
# ✅ [1/10] Scanning for XSS... 5 findings
# ✅ [2/10] Scanning for SQLi... 2 findings
# ✅ [3/10] Scanning for LFI... 1 findings
# ... dan seterusnya ...
# 
# 📄 Generating validation report...
# ✅ HTML Validation Report: ~/BUGx/results/example_com/VALIDATION_REPORT.html
# 
# Buka HTML report di browser, follow validation steps, submit bugs!
```

### Single Vulnerability Scan
```bash
$ python3 run.py
Select mode (1-11): 1  # XSS only
Enter target domain: testphp.vulnweb.com
Enter scan speed: 50
```

## 📊 Results

### AUTO HUNT Mode Output

**HTML Report** (Interactive validation checklist):
```
~/BUGx/results/<target>/VALIDATION_REPORT.html
```

Features:
- ✅ Beautiful visual dashboard with severity coloring
- ✅ Confidence score for each bug (85%+, 50-84%, <50%)
- ✅ Step-by-step validation guide
- ✅ Checkbox untuk track progress
- ✅ PoC suggestions
- ✅ Bounty potential estimates

**Consolidated JSON** (All findings):
```
~/BUGx/results/<target>/ALL_FINDINGS.json
```

### Single Mode Output

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

## 🎯 Typical Workflow

### For Bug Bounty Hunters:

```
Day 1: Setup (one-time)
├── ./setup.sh (30 minutes)
└── source activate.sh

Day 2+: Hunt bugs (repeat for each target)
├── python3 run.py
├── Select mode: 11 (AUTO HUNT)
├── Input: target.com
├── Wait: 30-60 minutes (go drink coffee ☕)
└── Results: 10-25 potential bugs

Day 2+: Validate & Submit
├── Open: ~/BUGx/results/target.com/VALIDATION_REPORT.html
├── For each bug:
│   ├── Read validation steps
│   ├── Follow the steps exactly
│   ├── Screenshot proof
│   └── Mark as validated ✅
└── Submit to bug bounty program → Get paid! 💰

Expected ROI:
├── Time investment: 4-8 hours (mostly validation)
├── Potential findings: 10-25 bugs
└── Bounty range: $500 - $25,000+ (depends on severity & program)
```

## 📚 Documentation

- [Quick Start Guide](QUICK_START.md) - Get started quickly
- [Installation Guide](INSTALLATION_GUIDE.md) - Detailed installation
- [laporan.txt](laporan.txt) - Project documentation (Indonesian)
- [prompt.txt](prompt.txt) - AI context for development
- [EXAMPLE_VALIDATION_REPORT.md](EXAMPLE_VALIDATION_REPORT.md) - Example output

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
