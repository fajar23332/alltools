package main

import (
	"autohunt/internal/core"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"strings"
)

const (
	moduleNuclei = "nuclei"
	moduleFFUF   = "ffuf"
)

// Desain baru (eksternal-only, sesuai permintaan):
//
// - Semua vulnerability scanning menggunakan nuclei.
// - Semua recon dan fuzzing menggunakan tools eksternal:
//   - subfinder, httpx, gau, nuclei, ffuf.
// - Tidak ada modul vuln internal lagi.
//
// Mode:
//
// 1) Default:
//    autohunt -u target
//    - subfinder -d <domain>
//    - httpx dari hasil subfinder (mc=200)
//    - nuclei -l <list> -c <concurrency>
//    - tanpa --severity khusus
//
// 2) -F / --fullpower:
//    autohunt -u target -F
//    - Sama seperti default (explicit), subfinder + httpx + nuclei.
//
// 3) -fa / --fullpower-aggressive:
//    autohunt -u target -fa
//    - subfinder -d <domain>
//    - httpx -l subs.txt -mc 200
//    - gau dari hasil httpx
//    - httpx -l gau.txt -mc 200
//    - nuclei -l clean.txt -c <concurrency> --severity medium,high,critical
//
// 4) -tags:
//    autohunt -u target --tags <tag1,tag2,...>
//    - subfinder + httpx
//    - nuclei -l <list> -c <concurrency> -tags <tags>
//
// 5) -fuzzing (standalone):
//    autohunt -u https://target.com/FUZZ -fuzzing [-v] [-c N]
//    - ffuf -u <target> -w wordlists/dirs_common.txt -mc 200 -r -t <c>
//    - jika -v → tambahkan -v ke ffuf
//    - tidak menjalankan recon/nuclei
//
// Catatan penting:
// - Semua file sementara (subs.txt, httpx.txt, gau.txt, clean.txt, nuclei_targets.txt) dibuat
//   di direktori temporary dan DIHAPUS setelah selesai.
// - Jika binary eksternal tidak tersedia, mode terkait akan fail jelas.
// - -F adalah versi ringan di bawah -fa (tanpa gau, tanpa severity khusus).
// - gau hanya digunakan di -fa, setelah httpx dari subfinder.

func main() {
	// CLI flags
	target := flag.String("u", "", "Single target URL or domain (e.g. https://example.com or example.com)")
	targetsFile := flag.String("f", "", "File with list of targets (one per line)")
	output := flag.String("o", "autohunt_result.json", "Output JSON file for nuclei results")
	concurrency := flag.Int("c", 10, "Maximum concurrency for external tools (nuclei, ffuf, httpx, etc.)")
	verbose := flag.Bool("v", false, "Verbose output (show external tool commands/output)")
	fuzzing := flag.Bool("fuzzing", false, "Run ffuf-only fuzzing mode against target (standalone if used without -F/-fa/--tags)")
	tagsFilter := flag.String("tags", "", "Comma-separated tags passed directly to nuclei as --tags")

	// Mode:
	fullpower := flag.Bool("fullpower", false, "Fullpower mode: subfinder + httpx + nuclei (explicit, ringan)")
	flag.BoolVar(fullpower, "F", false, "Alias for --fullpower")

	fullpowerAggressive := flag.Bool("fullpower-aggressive", false, "Aggressive mode: subfinder + httpx + gau + httpx + nuclei --severity medium,high,critical")
	flag.BoolVar(fullpowerAggressive, "fa", false, "Alias for --fullpower-aggressive")

	flag.Parse()

	stageBanner("STAGE 1: TARGET INITIALIZATION")

	if *target == "" && *targetsFile == "" {
		log.Fatalf("[!] Please provide -u <target> or -f <file> (single target mode is recommended for this design)")
	}
	if *targetsFile != "" {
		log.Fatalf("[!] File mode (-f) is not supported in this external-only CLI yet; use -u with single target")
	}

	rawTarget := strings.TrimSpace(*target)
	if rawTarget == "" {
		log.Fatalf("[!] Invalid target")
	}

	// Normalize: jika tanpa scheme, asumsikan https
	if !strings.HasPrefix(rawTarget, "http://") && !strings.HasPrefix(rawTarget, "https://") {
		rawTarget = "https://" + rawTarget
	}

	fmt.Printf("[*] Target: %s\n", rawTarget)

	// Standalone -fuzzing mode (tidak boleh bercampur dengan -F / -fa / --tags)
	if *fuzzing && !*fullpower && !*fullpowerAggressive && *tagsFilter == "" {
		stageBanner("STANDALONE FFUF MODE (-fuzzing)")
		if err := core.RunFFUFStandalone(rawTarget, *concurrency, *verbose); err != nil {
			log.Fatalf("[!] FFUF error: %v", err)
		}
		return
	}

	// Siapkan concurrency aman
	if *concurrency < 1 {
		*concurrency = 1
	}

	// Pastikan nuclei tersedia untuk semua mode selain standalone ffuf
	if !hasBinary(moduleNuclei) {
		log.Fatalf("[!] nuclei binary not found in PATH; install nuclei first")
	}

	// STAGE 2: RECON (external-only)
	stageBanner("STAGE 2: RECON")
	var nucleiInput []string

	switch {
	case *fullpowerAggressive:
		fmt.Println("[*] Mode: -fa (aggressive) -> subfinder + httpx + gau + httpx (mc=200)")
		var err error
		nucleiInput, err = runAggressiveRecon(rawTarget, *concurrency, *verbose)
		if err != nil {
			log.Fatalf("[!] Aggressive recon failed: %v", err)
		}

	case *fullpower:
		fmt.Println("[*] Mode: -F (fullpower ringan) -> subfinder + httpx (mc=200)")
		var err error
		nucleiInput, err = runLightRecon(rawTarget, *concurrency, *verbose)
		if err != nil {
			log.Fatalf("[!] Fullpower recon failed: %v", err)
		}

	case *tagsFilter != "":
		fmt.Println("[*] Mode: --tags -> subfinder + httpx, nuclei dengan --tags")
		var err error
		nucleiInput, err = runLightRecon(rawTarget, *concurrency, *verbose)
		if err != nil {
			log.Fatalf("[!] Tags recon failed: %v", err)
		}

	default:
		fmt.Println("[*] Mode: default -> subfinder + httpx (mc=200)")
		var err error
		nucleiInput, err = runLightRecon(rawTarget, *concurrency, *verbose)
		if err != nil {
			log.Fatalf("[!] Default recon failed: %v", err)
		}
	}

	if len(nucleiInput) == 0 {
		log.Fatalf("[!] Recon produced no URLs for nuclei")
	}

	// STAGE 3: NUCLEI SCANNING
	stageBanner("STAGE 3: NUCLEI SCANNING")

	// Tentukan opsi nuclei berdasarkan mode
	useSeverity := *fullpowerAggressive
	// -fa: gunakan --severity medium,high,critical
	// default / -F / --tags: tanpa --severity kecuali user atur via tags

	if err := runNuclei(nucleiInput, *concurrency, *verbose, *tagsFilter, useSeverity, *output); err != nil {
		log.Fatalf("[!] nuclei scan failed: %v", err)
	}

	// STAGE 4: Optional FFUF after nuclei (jika user minta, selain standalone)
	if *fuzzing {
		stageBanner("STAGE 4: FFUF FUZZING (-fuzzing)")
		if err := core.RunFFUFStandalone(rawTarget, *concurrency, *verbose); err != nil {
			log.Fatalf("[!] FFUF error: %v", err)
		}
	}

	fmt.Println("[+] Done.")
}

// =========================
// Helper: Stage banners
// =========================

func stageBanner(title string) {
	fmt.Println()
	fmt.Println("==================================================")
	fmt.Println(title)
	fmt.Println("==================================================")
}

// =========================
// Helper: binary check
// =========================

func hasBinary(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

// =========================
// Recon pipelines & helpers
// =========================

// runSubfinder runs:
// verbose:   subfinder -d <domain>
// non-verb:  subfinder -d <domain> -silent
func runSubfinder(domain string, conc int, verbose bool) ([]string, error) {
	if !hasBinary("subfinder") {
		return nil, fmt.Errorf("subfinder not found")
	}

	args := []string{"-d", domain}
	if !verbose {
		args = append(args, "-silent")
	}
	if conc > 0 {
		args = append(args, "-t", fmt.Sprintf("%d", conc))
	}

	if verbose {
		fmt.Printf("[cmd] subfinder %s\n", strings.Join(args, " "))
	}

	cmd := exec.Command("subfinder", args...)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("subfinder failed: %w", err)
	}

	lines := splitLines(string(out))
	if verbose {
		fmt.Printf("[subfinder] %d results\n", len(lines))
	}
	return lines, nil
}

// runHttpxFromList runs httpx with mc=200 on stdin list.
func runHttpxFromList(input []string, conc int, verbose bool) ([]string, error) {
	if !hasBinary("httpx") {
		return nil, fmt.Errorf("httpx not found")
	}
	if len(input) == 0 {
		return nil, nil
	}

	args := []string{"-mc", "200"}
	if !verbose {
		args = append(args, "-silent")
	}
	if conc > 0 {
		args = append(args, "-t", fmt.Sprintf("%d", conc))
	}

	if verbose {
		fmt.Printf("[cmd] httpx %s\n", strings.Join(args, " "))
	}

	cmd := exec.Command("httpx", args...)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("httpx stdin: %w", err)
	}
	outPipe, err := cmd.StdoutPipe()
	if err != nil {
		return nil, fmt.Errorf("httpx stdout: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("httpx start: %w", err)
	}

	go func() {
		defer stdin.Close()
		for _, l := range input {
			l = strings.TrimSpace(l)
			if l != "" {
				_, _ = fmt.Fprintln(stdin, l)
			}
		}
	}()

	outBytes, err := io.ReadAll(outPipe)
	if err != nil {
		return nil, fmt.Errorf("httpx read: %w", err)
	}

	_ = cmd.Wait()

	lines := splitLines(string(outBytes))
	if verbose {
		fmt.Printf("[httpx] %d results (mc=200)\n", len(lines))
	}
	return lines, nil
}

// runAggressiveRecon: subfinder -> httpx -> gau -> httpx
func runAggressiveRecon(rawTarget string, conc int, verbose bool) ([]string, error) {
	domain := extractDomain(rawTarget)
	if domain == "" {
		return nil, fmt.Errorf("unable to extract domain from %s", rawTarget)
	}
	// subfinder
	subs, err := runSubfinder(domain, conc, verbose)
	if err != nil || len(subs) == 0 {
		return nil, fmt.Errorf("subfinder failed or empty")
	}
	// httpx on subs
	live1, err := runHttpxFromList(subs, conc, verbose)
	if err != nil || len(live1) == 0 {
		return nil, fmt.Errorf("httpx(subfinder) failed or empty")
	}
	// gau on live1
	gauURLs, err := runGauFromList(live1, conc, verbose)
	if err != nil || len(gauURLs) == 0 {
		return nil, fmt.Errorf("gau failed or empty")
	}
	// httpx on gauURLs
	clean, err := runHttpxFromList(gauURLs, conc, verbose)
	if err != nil || len(clean) == 0 {
		return nil, fmt.Errorf("httpx(gau) failed or empty")
	}
	return clean, nil
}

// runLightRecon: subfinder -> httpx
func runLightRecon(rawTarget string, conc int, verbose bool) ([]string, error) {
	domain := extractDomain(rawTarget)
	if domain == "" {
		return nil, fmt.Errorf("unable to extract domain from %s", rawTarget)
	}
	subs, err := runSubfinder(domain, conc, verbose)
	if err != nil || len(subs) == 0 {
		return nil, fmt.Errorf("subfinder failed or empty")
	}
	live, err := runHttpxFromList(subs, conc, verbose)
	if err != nil || len(live) == 0 {
		return nil, fmt.Errorf("httpx(subfinder) failed or empty")
	}
	return live, nil
}

// runGauFromList: simple sequential gau over hosts list.
func runGauFromList(hosts []string, conc int, verbose bool) ([]string, error) {
	if !hasBinary("gau") {
		return nil, fmt.Errorf("gau not found")
	}
	var outAll []string
	for _, h := range hosts {
		h = strings.TrimSpace(h)
		if h == "" {
			continue
		}
		args := []string{}
		if conc > 0 {
			args = append(args, fmt.Sprintf("--threads=%d", conc))
		}
		args = append(args, h)
		if verbose {
			fmt.Printf("[cmd] gau %s\n", strings.Join(args, " "))
		}
		cmd := exec.Command("gau", args...)
		out, err := cmd.Output()
		if err != nil {
			if verbose {
				fmt.Printf("[gau] error on %s: %v\n", h, err)
			}
			continue
		}
		lines := splitLines(string(out))
		if verbose && len(lines) > 0 {
			fmt.Printf("[gau] %s -> %d URLs\n", h, len(lines))
		}
		outAll = append(outAll, lines...)
	}
	return outAll, nil
}

// =========================
// nuclei orchestration
// =========================

func runNuclei(urls []string, conc int, verbose bool, tags string, aggressive bool, output string) error {
	if len(urls) == 0 {
		return fmt.Errorf("no targets for nuclei")
	}

	// Tulis targets ke file sementara
	tmpFile, err := os.CreateTemp("", "autohunt-nuclei-targets-*.txt")
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	defer os.Remove(tmpFile.Name())

	for _, u := range urls {
		u = strings.TrimSpace(u)
		if u != "" {
			_, _ = tmpFile.WriteString(u + "\n")
		}
	}
	_ = tmpFile.Close()

	args := []string{
		"-l", tmpFile.Name(),
		"-c", fmt.Sprintf("%d", conc),
		"-json",
		"-o", output,
	}

	if aggressive {
		args = append(args, "--severity", "medium,high,critical")
	}
	if tags != "" {
		args = append(args, "-tags", tags)
	}

	if verbose {
		fmt.Printf("[cmd] nuclei %s\n", strings.Join(args, " "))
	}

	cmd := exec.Command(moduleNuclei, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return cmd.Run()
}

// =========================
// Utility helpers
// =========================

// splitLines converts a raw string into a slice of non-empty trimmed lines.
func splitLines(s string) []string {
	var out []string
	for _, line := range strings.Split(s, "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			out = append(out, line)
		}
	}
	return out
}

// extractDomain normalizes target to a domain for subfinder.
func extractDomain(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	// If it already looks like a bare domain.
	if !strings.HasPrefix(raw, "http://") && !strings.HasPrefix(raw, "https://") {
		return raw
	}
	// Strip scheme.
	withoutScheme := raw
	if i := strings.Index(withoutScheme, "://"); i != -1 {
		withoutScheme = withoutScheme[i+3:]
	}
	// Take up to first slash.
	if i := strings.Index(withoutScheme, "/"); i != -1 {
		withoutScheme = withoutScheme[:i]
	}
	return strings.TrimSpace(withoutScheme)
}
