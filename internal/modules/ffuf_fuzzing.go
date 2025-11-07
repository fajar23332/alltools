package modules

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"autohunt/internal/core"
)

// FFUF fuzzing helper:
// - Hanya dijalankan jika user set --fuzzing.
// - Hanya menjalankan SATU proses ffuf.
// - Menggunakan wordlists/dirs_common.txt sebagai wordlist wajib.
// - Target wajib berupa URL dengan placeholder FUZZ, misalnya: https://example.com/FUZZ
//   - Jika target tidak mengandung "FUZZ", auto-append "/FUZZ" pada URL target pertama.
// - Filter hasil dengan -mc 200 saja.
// - Thread ffuf diambil dari -c autohunt (dengan batas aman).
// - Jika -o autohunt diset: hasil ffuf diparse dan dimasukkan ke findings JSON.
// - Jika -o tidak diset: hanya tampilkan live output ffuf (terutama saat -v).

const (
	ffufModuleName       = "FFUF"
	ffufWordlistRelative = "wordlists/dirs_common.txt"
)

// RunFFUFFuzzing:
//   - Menjalankan SATU ffuf dengan:
//     -u <target_URL_dengan_FUZZ>
//     -w wordlists/dirs_common.txt
//     -mc 200
//     -t <concurrency_dari_autohunt>
//   - Jika target pertama bukan URL lengkap (tanpa skema), dianggap gagal (tidak jalan).
//   - Jika -o autohunt dipakai, stdout ffuf diparse jadi Findings dan masuk JSON.
//   - Jika -o tidak dipakai, behavior praktis: tampilkan output ffuf (via -v) tanpa parsing berat.
func RunFFUFFuzzing(ctx *core.ScanContext, concurrency int, verbose bool) ([]core.Finding, error) {
	if ctx == nil || len(ctx.Targets) == 0 {
		return nil, nil
	}

	// Pastikan ffuf tersedia
	if !binaryExists("ffuf") {
		if verbose {
			fmt.Println("[FFUF] ffuf binary not found in PATH, skipping --fuzzing")
		}
		return nil, nil
	}

	// Resolve wordlist dirs_common.txt
	wordlistPath := resolveWordlistPath(ffufWordlistRelative)
	if wordlistPath == "" {
		if verbose {
			fmt.Printf("[FFUF] Wordlist %s not found, skipping --fuzzing\n", ffufWordlistRelative)
		}
		return nil, nil
	}

	// Ambil target pertama dari ScanContext
	if len(ctx.Targets) == 0 || ctx.Targets[0].URL == "" {
		if verbose {
			fmt.Println("[FFUF] No valid primary target URL, skipping --fuzzing")
		}
		return nil, nil
	}
	baseURL := ctx.Targets[0].URL

	// Wajib URL dengan skema (https:// atau http://)
	if !strings.HasPrefix(baseURL, "http://") && !strings.HasPrefix(baseURL, "https://") {
		if verbose {
			fmt.Printf("[FFUF] Invalid target for --fuzzing (must be full URL with scheme): %s\n", baseURL)
		}
		return nil, nil
	}

	// Pastikan mengandung FUZZ, kalau tidak, append /FUZZ
	fuzzURL := ensureFUZZURL(baseURL)

	// Threads dari -c autohunt, dengan batas aman
	ffufThreads := concurrency
	if ffufThreads <= 0 {
		ffufThreads = 10
	}
	if ffufThreads > 80 {
		ffufThreads = 80
	}

	if verbose {
		fmt.Println("==================================================")
		fmt.Println("FFUF FUZZING (--fuzzing)")
		fmt.Println("==================================================")
		fmt.Printf("[FFUF] Target base URL : %s\n", baseURL)
		fmt.Printf("[FFUF] Fuzz URL        : %s\n", fuzzURL)
		fmt.Printf("[FFUF] Wordlist        : %s\n", wordlistPath)
		fmt.Printf("[FFUF] Threads         : %d\n", ffufThreads)
	}

	// Selalu gunakan -mc 200 sesuai requirement baru.
	// -o:
	//   - Jika autohunt memakai output JSON, fungsi ini sudah memparse stdout menjadi findings.
	//   - Jika tidak, ffuf akan menampilkan output apa adanya (terutama saat -v).
	args := []string{
		"-u", fuzzURL,
		"-w", wordlistPath,
		"-mc", "200",
		"-t", fmt.Sprintf("%d", ffufThreads),
	}

	// Untuk menjaga kompatibilitas dengan desain lama:
	// - Saat verbose: biarkan output asli ffuf tampil (stdout+stderr).
	// - Saat non-verbose: tetap baca stdout untuk membangun findings tanpa membuat file terpisah.
	cmd := exec.Command("ffuf", args...)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		if verbose {
			fmt.Printf("[FFUF] Failed to attach stdout: %v\n", err)
		}
		return nil, nil
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		if verbose {
			fmt.Printf("[FFUF] Failed to attach stderr: %v\n", err)
		}
		return nil, nil
	}

	if err := cmd.Start(); err != nil {
		if verbose {
			fmt.Printf("[FFUF] Failed to start ffuf: %v\n", err)
		}
		return nil, nil
	}

	var findings []core.Finding

	// Stream stderr jika verbose
	if verbose {
		go func() {
			buf := make([]byte, 4096)
			for {
				n, rerr := stderr.Read(buf)
				if n > 0 {
					fmt.Printf("%s", string(buf[:n]))
				}
				if rerr != nil {
					break
				}
			}
		}()
	} else {
		// Jika tidak verbose, buang stderr supaya tidak ganggu output
		go func() {
			_, _ = io.Copy(os.Stderr, stderr)
		}()
	}

	// Baca stdout:
	// - Jika autohunt pakai output JSON: parse setiap baris URL menjadi Finding.
	// - Jika tidak, user tetap bisa lihat output ffuf bila -v aktif.
	scanner := bufio.NewScanner(stdout)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		if verbose {
			fmt.Println(line)
		}

		// Asumsikan format standar: URL ada di line.
		if strings.HasPrefix(line, "http://") || strings.HasPrefix(line, "https://") {
			f := core.Finding{
				Target:     baseURL,
				Endpoint:   line,
				Module:     ffufModuleName,
				Type:       "Potential Sensitive Path (ffuf)",
				Severity:   "Info",
				Confidence: 0.6,
				Evidence:   fmt.Sprintf("Discovered via ffuf using %s", filepath.Base(wordlistPath)),
				Tags:       []string{"sensitive(ffuf)", "fuzzing"},
			}
			findings = append(findings, f)
		}
	}

	_ = cmd.Wait()

	if verbose {
		fmt.Printf("[FFUF] Total findings from ffuf: %d\n", len(findings))
	}

	return findings, nil
}

// binaryExists checks if a binary is available in PATH.
func binaryExists(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

// resolveWordlistPath tries to resolve a wordlist path relative to CWD and repo layout.
func resolveWordlistPath(rel string) string {
	// check literal relative
	if st, err := os.Stat(rel); err == nil && !st.IsDir() {
		return rel
	}

	// check ./wordlists/...
	if st, err := os.Stat(filepath.Join(".", rel)); err == nil && !st.IsDir() {
		return filepath.Join(".", rel)
	}

	return ""
}

// ensureFUZZURL ensures the given base URL contains "FUZZ" placeholder.
// If missing, it appends "/FUZZ" appropriately.
func ensureFUZZURL(base string) string {
	if strings.Contains(base, "FUZZ") {
		return base
	}
	if strings.HasSuffix(base, "/") {
		return base + "FUZZ"
	}
	return base + "/FUZZ"
}

// extractURLFromFFUFLine tries to parse a URL from a ffuf stdout line.
// This is a best-effort heuristic that treats the first "http" substring
// as the URL start and trims trailing junk.
func extractURLFromFFUFLine(line string) string {
	// Skip comment / meta lines
	if strings.HasPrefix(line, "#") {
		return ""
	}

	// Find http/https
	idx := strings.Index(line, "http")
	if idx == -1 {
		return ""
	}
	url := strings.TrimSpace(line[idx:])

	// Cut on space if ffuf outputs extra columns
	if sp := strings.IndexAny(url, " \t"); sp != -1 {
		url = url[:sp]
	}

	if url == "" || !strings.HasPrefix(url, "http") {
		return ""
	}
	return url
}

// deriveTargetForURL is available in other modules and reused there.
// We intentionally do not redefine it here to avoid duplicate symbol errors.
