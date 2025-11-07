package modules

import (
	"bufio"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"autohunt/internal/core"
)

// SensitiveFilesModule implements the legacy Module interface (Run with []Target).
// Kept for backward compatibility if needed elsewhere.
type SensitiveFilesModule struct {
	paths []string
}

func NewSensitiveFilesModule() *SensitiveFilesModule {
	return &SensitiveFilesModule{
		paths: []string{
			"/.git/config",
			"/.env",
			"/.env.backup",
			"/.env.bak",
			"/backup.sql",
			"/db.sql",
			"/config.php.bak",
			"/web.config.bak",
			"/.DS_Store",
		},
	}
}

func (m *SensitiveFilesModule) Name() string {
	return "SensitiveFiles"
}

func (m *SensitiveFilesModule) Run(targets []core.Target) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	for _, t := range targets {
		for _, p := range m.paths {
			url := t.URL + p
			req, _ := http.NewRequest("GET", url, nil)
			resp, err := client.Do(req)
			if err != nil {
				continue
			}
			if resp.Body != nil {
				resp.Body.Close()
			}

			if resp.StatusCode == 200 {
				findings = append(findings, core.Finding{
					Target:     t.URL,
					Endpoint:   url,
					Module:     m.Name(),
					Type:       "Sensitive File Exposure",
					Severity:   "High",
					Confidence: 0.9,
					Evidence:   fmt.Sprintf("HTTP %d on %s", resp.StatusCode, url),
					Tags:       []string{"sensitive", "exposed"},
				})
			}
		}
	}

	return findings, nil
}

// SensitiveFilesContextModule adapts SensitiveFiles scanning to the ContextModule
// interface, using ScanContext.Targets as the source of base URLs.
// Dalam mode agresif (-fa), modul ini juga memuat wordlist dirs_common.txt (jika ada)
// untuk melakukan fuzzing path sensitif tambahan secara terarah namun tetap dibatasi.
type SensitiveFilesContextModule struct {
	paths []string
}

func NewSensitiveFilesContextModule() *SensitiveFilesContextModule {
	return &SensitiveFilesContextModule{
		paths: []string{
			"/.git/config",
			"/.env",
			"/.env.backup",
			"/.env.bak",
			"/backup.sql",
			"/db.sql",
			"/config.php.bak",
			"/web.config.bak",
			"/.DS_Store",
		},
	}
}

func (m *SensitiveFilesContextModule) Name() string {
	return "SensitiveFiles"
}

func (m *SensitiveFilesContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	// Base paths selalu dicek (mode normal & fullpower)
	paths := append([]string{}, m.paths...)

	// Jika mode agresif aktif (--fullpower-aggressive / -fa),
	// muat wordlist dirs_common.txt sebagai tambahan path fuzzing yang terarah.
	if ctx != nil && ctx.IsAggressive() {
		wordlistPaths := loadDirsWordlist()
		// Batasi jumlah tambahan agar tetap aman
		maxExtra := 300
		for i, p := range wordlistPaths {
			if i >= maxExtra {
				break
			}
			if p == "" {
				continue
			}
			// Normalisasi: pastikan diawali dengan "/"
			if p[0] != '/' {
				p = "/" + p
			}
			paths = append(paths, p)
		}
	}

	for _, t := range ctx.Targets {
		for _, p := range paths {
			url := t.URL + p
			req, _ := http.NewRequest("GET", url, nil)
			resp, err := client.Do(req)
			if err != nil {
				continue
			}
			if resp.Body != nil {
				resp.Body.Close()
			}

			if resp.StatusCode == 200 {
				findings = append(findings, core.Finding{
					Target:     t.URL,
					Endpoint:   url,
					Module:     m.Name(),
					Type:       "Sensitive File or Path Exposure",
					Severity:   "High",
					Confidence: 0.9,
					Evidence:   fmt.Sprintf("HTTP %d on %s", resp.StatusCode, url),
					Tags:       []string{"sensitive", "exposed"},
				})
			}
		}
	}

	return findings, nil
}

// loadDirsWordlist memuat wordlists/dirs_common.txt jika tersedia.
// Digunakan hanya pada mode agresif untuk memperluas cakupan path secara aman.
func loadDirsWordlist() []string {
	// Cari file relatif terhadap working directory saat ini.
	candidates := []string{
		"wordlists/dirs_common.txt",
		filepath.Join(".", "wordlists", "dirs_common.txt"),
	}

	for _, path := range candidates {
		f, err := os.Open(path)
		if err != nil {
			continue
		}
		defer f.Close()

		var lines []string
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			line := sc.Text()
			if line == "" || line[0] == '#' {
				continue
			}
			lines = append(lines, line)
		}
		if len(lines) > 0 {
			return lines
		}
	}

	return nil
}
