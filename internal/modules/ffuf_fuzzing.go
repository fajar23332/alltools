package modules

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"autohunt/internal/core"
)

// FFUFFuzzingModule provides a helper to run ffuf-based fuzzing as an optional,
// clearly separated step from the main recon + vulnerability scanning pipeline.
//
// Design goals:
// - Triggered ONLY when user passes --fuzzing
// - Uses a single, unified wordlist: wordlists/dirs_common.txt
// - Ensures the ffuf target URL contains FUZZ (auto-append /FUZZ if needed)
// - Non-destructive: only performs GET requests (ffuf default) with status-code filtering
// - Bounded: avoids unbounded brute-force by:
//   - Requiring explicit opt-in (--fuzzing)
//   - Using the provided concurrency
//   - Fuzzing only the main/primary target(s), not every discovered URL
// - Integrates results into autohunt_result.json as findings:
//   - Module: "FFUF"
//   - Tags: ["sensitive(ffuf)", "fuzzing"]
//
// NOTE:
// - This module assumes ffuf binary is available in PATH (setup.sh attempts to install/copy it).
// - If ffuf is missing or fails, it will return gracefully without breaking the main scan.

const (
	ffufModuleName         = "FFUF"
	ffufWordlistRelative   = "wordlists/dirs_common.txt"
	ffufDefaultStatusCodes = "200,204,301,302,307,401,403"
)

// RunFFUFFuzzing runs ffuf-based path fuzzing against the primary targets
// in the given ScanContext, using the unified dirs_common.txt wordlist.
//
// Parameters:
// - ctx: Full ScanContext produced by FullRecon / pipeline
// - concurrency: desired max concurrency (will be capped for safety)
// - verbose: whether to show ffuf command and streaming output
//
// Behavior:
//   - Determine base URL(s) to fuzz from ctx.Targets
//     (for now we fuzz only the first valid target URL to stay controlled).
//   - Ensure the fuzzing URL includes FUZZ:
//   - If not, append "/FUZZ" to the base URL.
//   - Run ffuf with:
//     ffuf -u <fuzzURL> -w wordlists/dirs_common.txt -mc 200,204,301,302,307,401,403 -r -c -t <N>
//   - Parse ffuf stdout lines that contain results and convert them into Findings.
//   - Does NOT create persistent temp files; works via streaming.
//
// If ffuf is not available or wordlist missing, returns (nil, nil) quietly.
func RunFFUFFuzzing(ctx *core.ScanContext, concurrency int, verbose bool) ([]core.Finding, error) {
	if ctx == nil || len(ctx.Targets) == 0 {
		return nil, nil
	}

	// Check ffuf binary
	if !binaryExists("ffuf") {
		if verbose {
			fmt.Println("[FFUF] ffuf binary not found in PATH, skipping --fuzzing")
		}
		return nil, nil
	}

	// Resolve wordlist path
	wordlistPath := resolveWordlistPath(ffufWordlistRelative)
	if wordlistPath == "" {
		if verbose {
			fmt.Printf("[FFUF] Wordlist %s not found, skipping --fuzzing\n", ffufWordlistRelative)
		}
		return nil, nil
	}

	// Cap concurrency for ffuf to avoid abuse
	ffufThreads := concurrency
	if ffufThreads <= 0 {
		ffufThreads = 10
	}
	if ffufThreads > 80 {
		ffufThreads = 80
	}

	// Choose primary target URL to fuzz.
	// For now: use the first target's URL as base.
	baseURL := ctx.Targets[0].URL
	if baseURL == "" {
		return nil, nil
	}

	fuzzURL := ensureFUZZURL(baseURL)

	if verbose {
		fmt.Println("==================================================")
		fmt.Println("FFUF FUZZING (--fuzzing)")
		fmt.Println("==================================================")
		fmt.Printf("[FFUF] Target base URL : %s\n", baseURL)
		fmt.Printf("[FFUF] Fuzz URL        : %s\n", fuzzURL)
		fmt.Printf("[FFUF] Wordlist        : %s\n", wordlistPath)
		fmt.Printf("[FFUF] Threads         : %d\n", ffufThreads)
	}

	args := []string{
		"-u", fuzzURL,
		"-w", wordlistPath,
		"-mc", ffufDefaultStatusCodes,
		"-r", // follow redirects per request
		"-c", // colorized output (harmless in terminal; parsing ignores colors)
		"-t", fmt.Sprintf("%d", ffufThreads),
		"-o", "-", // use stdout; results parsed from stdout
	}

	// Run ffuf
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

	findingsChan := make(chan core.Finding, 256)

	// Stream stderr (informational) if verbose
	if verbose {
		go func() {
			sc := bufio.NewScanner(stderr)
			for sc.Scan() {
				line := strings.TrimSpace(sc.Text())
				if line == "" {
					continue
				}
				fmt.Printf("[FFUF][err] %s\n", line)
			}
		}()
	}

	// Parse stdout: ffuf default stdout includes result lines.
	// Since formats can vary, we parse conservatively:
	// - Look for lines containing "http" and not starting with "#" or "[" only.
	go func() {
		sc := bufio.NewScanner(stdout)
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" {
				continue
			}

			if verbose {
				fmt.Printf("[FFUF][out] %s\n", line)
			}

			url := extractURLFromFFUFLine(line)
			if url == "" {
				continue
			}

			target := deriveTargetForURL(ctx, url)
			f := core.Finding{
				Target:     target,
				Endpoint:   url,
				Module:     ffufModuleName,
				Type:       "Potential Sensitive Path (ffuf)",
				Severity:   "Info",
				Confidence: 0.6,
				Evidence:   fmt.Sprintf("Discovered via ffuf using %s", filepath.Base(wordlistPath)),
				Tags:       []string{"sensitive(ffuf)", "fuzzing"},
			}
			findingsChan <- f
		}
		close(findingsChan)
	}()

	// Wait for ffuf to exit with a bounded wait
	waitCh := make(chan error, 1)
	go func() {
		waitCh <- cmd.Wait()
	}()

	select {
	case err := <-waitCh:
		if err != nil && verbose {
			fmt.Printf("[FFUF] ffuf exited with error: %v\n", err)
		}
	case <-time.After(5 * time.Minute):
		// Timeout safeguard for extreme cases
		if verbose {
			fmt.Println("[FFUF] ffuf timed out after 5 minutes, killing process.")
		}
		_ = cmd.Process.Kill()
	}

	// Collect findings
	var findings []core.Finding
	for f := range findingsChan {
		findings = append(findings, f)
	}

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
