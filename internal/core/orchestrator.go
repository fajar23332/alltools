package core

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Orchestrator: external-only
//
// Sesuai permintaan, file ini menyediakan helper untuk:
// - Recon pakai subfinder + httpx (+ gau untuk -fa)
// - Vulnerability scanning pakai nuclei
// - Fuzzing pakai ffuf
//
// TANPA modul vuln internal. autohunt akan pakai fungsi-fungsi ini dari main.go.
//
// Mode yang didukung (intended mapping di main.go):
//
// 1) Default: autohunt -u target
//    - RunDefaultRecon:
//        subfinder + httpx (mc 200) -> URL list
//    - RunNucleiFromContext:
//        nuclei -l urls.txt -c <c>
//
// 2) -F / --fullpower
//    - Sama seperti default (explisit), pakai RunDefaultRecon + RunNucleiFromContext.
//
// 3) -fa / --fullpower-aggressive
//    - RunAggressiveExternalRecon:
//        subfinder -d -> subs.txt
//        httpx -l subs.txt -mc 200 -> httpx.txt
//        gau dari httpx.txt -> gau.txt
//        httpx -l gau.txt -mc 200 -> clean.txt
//    - RunNucleiFromContext dengan:
//        nuclei -l clean.txt -c <c> --severity medium,high,critical
//
// 4) -tags
//    - RunDefaultRecon:
//        subfinder + httpx
//    - RunNucleiFromContext:
//        nuclei -l urls.txt -c <c> -tags <tags>
//
// 5) -fuzzing (standalone)
//    - RunFFUFStandalone:
//        ffuf -u <target/FUZZ> -w wordlists/dirs_common.txt -mc 200 -r -t <c> (-v jika verbose)
//
// Catatan penting:
// - Semua file sementara dibuat di direktori temp via os.MkdirTemp dan dihapus dengan os.RemoveAll.
// - Tidak ada penulisan wordlists di sini; diasumsikan wordlists berasal dari repo autohunt.
// - Jika binary eksternal tidak ada, fungsi akan mengembalikan error terkontrol.
// - Parsing output nuclei di sini minimal: kita hanya pass-through ke file -o jika diset dari main,
//   atau biarkan nuclei menulis sendiri. Konversi ke Finding bisa ditambahkan kemudian jika dibutuhkan.

const (
	ffufWordlistRelative = "wordlists/dirs_common.txt"
)

// ------------- Helpers: Binary checks -------------

// NOTE: binaryExists is already defined in other core files (e.g. fullrecon.go).
// Do NOT redeclare it here to avoid duplicate symbol errors.

func HasNuclei() bool {
	return binaryExists("nuclei")
}

// ------------- Recon Modes -------------

// RunDefaultRecon:
// - subfinder (jika ada) -> subs
// - httpx (mc 200) -> urls
// - Mengisi ScanContext dengan LiveURLs dari hasil httpx.
func RunDefaultRecon(targets []Target, concurrency int, verbose bool) *ScanContext {
	ctx := &ScanContext{
		Targets:      targets,
		Concurrency:  concurrency,
		ExternalUsed: []string{},
	}

	if len(targets) == 0 {
		return ctx
	}

	t := targets[0]
	domain := normalizeDomainForExternal(t.URL)
	if domain == "" || !binaryExists("subfinder") || !binaryExists("httpx") {
		// fallback: tidak ada external tools, gunakan URL asli saja
		ctx.LiveURLs = []string{t.URL}
		return ctx
	}

	tmpDir, err := os.MkdirTemp("", "autohunt-default-*")
	if err != nil {
		ctx.LiveURLs = []string{t.URL}
		return ctx
	}
	defer os.RemoveAll(tmpDir)

	subsPath := filepath.Join(tmpDir, "subs.txt")
	httpxPath := filepath.Join(tmpDir, "httpx.txt")

	// subfinder
	subsCount, err := runSubfinderToFile(domain, subsPath, concurrency, verbose)
	if err != nil || subsCount == 0 {
		ctx.LiveURLs = []string{t.URL}
		return ctx
	}
	ctx.ExternalUsed = append(ctx.ExternalUsed, "subfinder")

	// httpx mc=200
	liveCount, urls, err := runHttpxListToFileAndSlice(subsPath, httpxPath, concurrency, verbose)
	if err != nil || liveCount == 0 {
		ctx.LiveURLs = []string{t.URL}
		return ctx
	}
	ctx.ExternalUsed = append(ctx.ExternalUsed, "httpx")
	ctx.LiveURLs = urls

	return ctx
}

// RunLightExternalRecon saat ini sama dengan RunDefaultRecon (explicit mode -F).
func RunLightExternalRecon(targets []Target, concurrency int, verbose bool) *ScanContext {
	return RunDefaultRecon(targets, concurrency, verbose)
}

// RunTagsRecon:
// - Sama seperti RunDefaultRecon untuk pengumpulan URL,
// - Mode tags akan diteruskan di RunNucleiFromContext (bukan di sini).
func RunTagsRecon(targets []Target, concurrency int, verbose bool) *ScanContext {
	return RunDefaultRecon(targets, concurrency, verbose)
}

// RunAggressiveExternalRecon:
// - Hanya dipakai untuk -fa.
// - subfinder -> httpx(mc 200) -> gau -> httpx(mc 200)
// - Hasil akhir (clean) menjadi LiveURLs.
func RunAggressiveExternalRecon(targets []Target, concurrency int, verbose bool) *ScanContext {
	ctx := &ScanContext{
		Targets:      targets,
		Concurrency:  concurrency,
		ExternalUsed: []string{},
		Aggressive:   true,
	}

	if len(targets) == 0 {
		return ctx
	}
	if !binaryExists("subfinder") || !binaryExists("httpx") || !binaryExists("gau") {
		// fallback ke RunDefaultRecon jika tool tidak lengkap
		return RunDefaultRecon(targets, concurrency, verbose)
	}

	t := targets[0]
	domain := normalizeDomainForExternal(t.URL)
	if domain == "" {
		return RunDefaultRecon(targets, concurrency, verbose)
	}

	tmpDir, err := os.MkdirTemp("", "autohunt-fa-*")
	if err != nil {
		return RunDefaultRecon(targets, concurrency, verbose)
	}
	defer os.RemoveAll(tmpDir)

	subsPath := filepath.Join(tmpDir, "subs.txt")
	httpxSubsPath := filepath.Join(tmpDir, "httpx_subs.txt")
	gauPath := filepath.Join(tmpDir, "gau.txt")
	cleanPath := filepath.Join(tmpDir, "clean.txt")

	// 1) subfinder
	subsCount, err := runSubfinderToFile(domain, subsPath, concurrency, verbose)
	if err != nil || subsCount == 0 {
		return RunDefaultRecon(targets, concurrency, verbose)
	}
	ctx.ExternalUsed = append(ctx.ExternalUsed, "subfinder")

	// 2) httpx pada subs
	httpx1Count, _, err := runHttpxListToFileAndSlice(subsPath, httpxSubsPath, concurrency, verbose)
	if err != nil || httpx1Count == 0 {
		return RunDefaultRecon(targets, concurrency, verbose)
	}
	ctx.ExternalUsed = append(ctx.ExternalUsed, "httpx")

	// 3) gau dari hasil httpx
	gauCount, err := runGauFromFile(httpxSubsPath, gauPath, concurrency, verbose)
	if err != nil || gauCount == 0 {
		return RunDefaultRecon(targets, concurrency, verbose)
	}
	ctx.ExternalUsed = append(ctx.ExternalUsed, "gau")

	// 4) httpx pada hasil gau
	httpx2Count, cleanURLs, err := runHttpxListToFileAndSlice(gauPath, cleanPath, concurrency, verbose)
	if err != nil || httpx2Count == 0 {
		return RunDefaultRecon(targets, concurrency, verbose)
	}
	ctx.ExternalUsed = append(ctx.ExternalUsed, "httpx")

	if verbose {
		fmt.Printf("[fa] Summary: subfinder=%d, httpx(subs)=%d, gau=%d, httpx(clean)=%d\n",
			subsCount, httpx1Count, gauCount, httpx2Count)
	} else {
		fmt.Printf("[fa] External pipeline summary: subfinder=%d, httpx(subs)=%d, gau=%d, httpx(clean)=%d\n",
			subsCount, httpx1Count, gauCount, httpx2Count)
	}

	ctx.LiveURLs = cleanURLs
	return ctx
}

// ------------- Nuclei Orchestration -------------

// RunNucleiFromContext:
// - Mengambil LiveURLs dari ScanContext,
// - Menulis ke file temp,
// - Menjalankan nuclei dengan argumen sesuai mode:
//   - default / -F    : nuclei -l targets.txt -c <c>
//   - -fa (aggressive): nuclei -l targets.txt -c <c> --severity medium,high,critical
//   - --tags          : nuclei -l targets.txt -c <c> -tags <tags>
//
// - Jika outputPath != "" → gunakan -json -o outputPath agar nuclei tulis JSON.
// - Jika outputPath == "" → nuclei tulis ke stdout (autohunt biarkan lewat).
func RunNucleiFromContext(ctx *ScanContext, concurrency int, verbose bool, tags string, outputPath string, aggressive bool, fullpower bool) error {
	if ctx == nil || len(ctx.LiveURLs) == 0 {
		return fmt.Errorf("no URLs available for nuclei")
	}
	if !HasNuclei() {
		return fmt.Errorf("nuclei binary not found in PATH")
	}

	tmpDir, err := os.MkdirTemp("", "autohunt-nuclei-*")
	if err != nil {
		return fmt.Errorf("failed to create temp dir for nuclei: %w", err)
	}
	defer os.RemoveAll(tmpDir)

	targetsFile := filepath.Join(tmpDir, "targets.txt")

	// Tulis LiveURLs ke file
	f, err := os.Create(targetsFile)
	if err != nil {
		return fmt.Errorf("failed to create nuclei targets file: %w", err)
	}
	for _, u := range ctx.LiveURLs {
		u = strings.TrimSpace(u)
		if u == "" {
			continue
		}
		_, _ = f.WriteString(u + "\n")
	}
	_ = f.Close()

	args := []string{
		"-l", targetsFile,
		"-c", fmt.Sprintf("%d", safeConcurrency(concurrency)),
	}

	// Mode agresif: tambahkan severity filter
	if aggressive {
		args = append(args, "--severity", "medium,high,critical")
	}

	// Mode tags: diteruskan ke nuclei
	if strings.TrimSpace(tags) != "" {
		args = append(args, "-tags", strings.TrimSpace(tags))
	}

	// Output handling:
	if strings.TrimSpace(outputPath) != "" {
		// nuclei tulis JSON langsung ke file outputPath
		args = append(args, "-json", "-o", outputPath)
	}

	if verbose {
		fmt.Printf("[nuclei] running: nuclei %s\n", strings.Join(args, " "))
	}

	cmd := exec.Command("nuclei", args...)

	// Stream stdout/stderr jika verbose dan tidak pakai -o (biar user lihat progress)
	if verbose && strings.TrimSpace(outputPath) == "" {
		stdout, _ := cmd.StdoutPipe()
		stderr, _ := cmd.StderrPipe()

		if err := cmd.Start(); err != nil {
			return fmt.Errorf("failed to start nuclei: %w", err)
		}

		go streamPrefixedPipe(stdout, "[nuclei][out]")
		go streamPrefixedPipe(stderr, "[nuclei][err]")

		if err := cmd.Wait(); err != nil {
			return fmt.Errorf("nuclei exited with error: %w", err)
		}
	} else {
		out, err := cmd.CombinedOutput()
		if verbose {
			fmt.Printf("%s", string(out))
		}
		if err != nil {
			return fmt.Errorf("nuclei error: %w", err)
		}
	}

	return nil
}

// ------------- FFUF Orchestration -------------

// RunFFUFStandalone:
//   - Mode -fuzzing standalone:
//     ffuf -u https://stripchat.com/FUZZ -w wordlists/dirs_common.txt -t 9999 -v -r -c -mc 200,302,301,307,401,403,405
//   - Implementasi disesuaikan agar selalu menggunakan kombinasi flag di atas untuk target yang diberikan.
func RunFFUFStandalone(rawTarget string, concurrency int, verbose bool) error {
	if rawTarget == "" {
		return fmt.Errorf("no target provided for ffuf")
	}
	if !binaryExists("ffuf") {
		return fmt.Errorf("ffuf binary not found in PATH")
	}

	// pastikan target memiliki FUZZ
	targetURL := rawTarget
	if !strings.Contains(targetURL, "FUZZ") {
		if strings.HasSuffix(targetURL, "/") {
			targetURL = targetURL + "FUZZ"
		} else {
			targetURL = targetURL + "/FUZZ"
		}
	}

	wordlist := resolveWordlistPath(ffufWordlistRelative)
	if wordlist == "" {
		return fmt.Errorf("ffuf wordlist not found: %s", ffufWordlistRelative)
	}

	// Override concurrency ke 9999 sesuai permintaan untuk mode -fuzzing ini.
	threads := 9999

	args := []string{
		"-u", targetURL,
		"-w", wordlist,
		"-t", fmt.Sprintf("%d", threads),
		"-v",
		"-r",
		"-c",
		"-mc", "200,302,301,307,401,403,405",
	}

	fmt.Printf("[ffuf] running: ffuf %s\n", strings.Join(args, " "))

	cmd := exec.Command("ffuf", args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return cmd.Run()
}

// RunFFUFFuzzingFromContext:
//   - Opsional: digunakan jika ingin menjalankan ffuf SESUDAH recon/nuclei
//     berdasarkan target utama dari ScanContext.
//   - Implementasi minimal: hanya panggil RunFFUFStandalone untuk target pertama.
func RunFFUFFuzzingFromContext(ctx *ScanContext, concurrency int, verbose bool) error {
	if ctx == nil || len(ctx.Targets) == 0 {
		return fmt.Errorf("no targets for ffuf from context")
	}
	return RunFFUFStandalone(ctx.Targets[0].URL, concurrency, verbose)
}

// ------------- Internal helpers -------------

func safeConcurrency(c int) int {
	if c <= 0 {
		return 10
	}
	if c > 200 {
		return 200
	}
	return c
}

// runSubfinderToFile menjalankan subfinder dan menyimpan hasil ke file.
func runSubfinderToFile(domain, outPath string, concurrency int, verbose bool) (int, error) {
	args := []string{"-d", domain, "-o", outPath}
	if concurrency > 0 {
		args = append(args, "-t", fmt.Sprintf("%d", concurrency))
	}
	if !verbose {
		args = append(args, "-silent")
	}

	if verbose {
		fmt.Printf("[subfinder] running: subfinder %s\n", strings.Join(args, " "))
	}

	cmd := exec.Command("subfinder", args...)
	out, err := cmd.CombinedOutput()
	if verbose && len(out) > 0 {
		fmt.Printf("%s", string(out))
	}
	if err != nil {
		return 0, fmt.Errorf("subfinder failed: %w", err)
	}

	data, err := os.ReadFile(outPath)
	if err != nil {
		return 0, fmt.Errorf("failed reading subfinder output: %w", err)
	}
	lines := countNonEmptyLines(string(data))
	return lines, nil
}

// runHttpxListToFileAndSlice:
// - Membaca input list dari file inputPath,
// - Menjalankan httpx dengan -l, menyimpan ke outPath,
// - Mengembalikan jumlah dan slice hasil (baris non-kosong).
func runHttpxListToFileAndSlice(inputPath, outPath string, concurrency int, verbose bool) (int, []string, error) {
	args := []string{
		"-l", inputPath,
		"-mc", "200",
		"-t", fmt.Sprintf("%d", safeConcurrency(concurrency)),
		"-o", outPath,
	}
	if !verbose {
		args = append(args, "-silent")
	}

	if verbose {
		fmt.Printf("[httpx] running: httpx %s\n", strings.Join(args, " "))
	}

	cmd := exec.Command("httpx", args...)
	out, err := cmd.CombinedOutput()
	if verbose && len(out) > 0 {
		fmt.Printf("%s", string(out))
	}
	if err != nil {
		return 0, nil, fmt.Errorf("httpx failed: %w", err)
	}

	data, err := os.ReadFile(outPath)
	if err != nil {
		return 0, nil, fmt.Errorf("failed reading httpx output: %w", err)
	}
	text := strings.TrimSpace(string(data))
	if text == "" {
		return 0, nil, nil
	}
	lines := strings.Split(text, "\n")
	return len(lines), lines, nil
}

// runGauFromFile:
// - Membaca list host/URL dari inputPath,
// - Untuk setiap baris, menjalankan `gau --threads=<c> <host>`,
// - Menulis semua hasil ke outPath.
// - Mengembalikan jumlah total baris URL yang dihasilkan.
func runGauFromFile(inputPath, outPath string, concurrency int, verbose bool) (int, error) {
	inData, err := os.ReadFile(inputPath)
	if err != nil {
		return 0, fmt.Errorf("failed reading httpx input for gau: %w", err)
	}
	hosts := strings.Split(strings.TrimSpace(string(inData)), "\n")

	outFile, err := os.Create(outPath)
	if err != nil {
		return 0, fmt.Errorf("failed to create gau output file: %w", err)
	}
	defer outFile.Close()

	total := 0
	for _, h := range hosts {
		h = strings.TrimSpace(h)
		if h == "" {
			continue
		}
		args := []string{
			fmt.Sprintf("--threads=%d", safeConcurrency(concurrency)),
			h,
		}
		if verbose {
			fmt.Printf("[gau] running: gau %s\n", strings.Join(args, " "))
		}
		cmd := exec.Command("gau", args...)
		out, err := cmd.CombinedOutput()
		if verbose && len(out) > 0 {
			sc := bufio.NewScanner(strings.NewReader(string(out)))
			for sc.Scan() {
				line := strings.TrimSpace(sc.Text())
				if line != "" {
					fmt.Printf("[gau] %s\n", line)
				}
			}
		}
		if err != nil {
			if verbose {
				fmt.Printf("[gau] error for %s: %v\n", h, err)
			}
			continue
		}
		if len(out) > 0 {
			if _, werr := outFile.Write(out); werr != nil {
				return total, fmt.Errorf("failed writing gau output: %w", werr)
			}
			if out[len(out)-1] != '\n' {
				_, _ = outFile.WriteString("\n")
			}
			total += countNonEmptyLines(string(out))
		}
	}

	return total, nil
}

// resolveWordlistPath mencari wordlist relatif terhadap working dir atau repo.
func resolveWordlistPath(rel string) string {
	// cek relative langsung
	if st, err := os.Stat(rel); err == nil && !st.IsDir() {
		return rel
	}
	// cek ./wordlists/...
	if st, err := os.Stat(filepath.Join(".", rel)); err == nil && !st.IsDir() {
		return filepath.Join(".", rel)
	}
	return ""
}

func countNonEmptyLines(s string) int {
	if s == "" {
		return 0
	}
	n := 0
	sc := bufio.NewScanner(strings.NewReader(s))
	for sc.Scan() {
		if strings.TrimSpace(sc.Text()) != "" {
			n++
		}
	}
	return n
}

func streamPrefixedPipe(r io.Reader, prefix string) {
	sc := bufio.NewScanner(r)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line != "" {
			fmt.Printf("%s %s\n", prefix, line)
		}
	}
}

// ------------- Optional: nuclei JSON -> Findings (placeholder) -------------

// ParseNucleiJSONToFindings dapat digunakan jika nanti ingin membaca output JSON nuclei
// dan memetakannya ke struct Finding. Saat ini disiapkan minimal.
func ParseNucleiJSONToFindings(jsonData []byte) ([]Finding, error) {
	type nucleiEvent struct {
		TemplateID string `json:"template-id"`
		Info       struct {
			Name     string   `json:"name"`
			Severity string   `json:"severity"`
			Tags     []string `json:"tags"`
		} `json:"info"`
		Host    string `json:"host"`
		Matched string `json:"matched-at"`
	}
	var events []nucleiEvent
	if err := json.Unmarshal(jsonData, &events); err != nil {
		return nil, err
	}

	var out []Finding
	for _, e := range events {
		severity := strings.Title(strings.ToLower(e.Info.Severity))
		if severity == "" {
			severity = "Info"
		}
		f := Finding{
			Target:     e.Host,
			Endpoint:   e.Matched,
			Module:     "nuclei",
			Type:       e.TemplateID,
			Severity:   severity,
			Confidence: 0.9,
			Evidence:   e.Info.Name,
			Tags:       append([]string{"nuclei"}, e.Info.Tags...),
		}
		out = append(out, f)
	}
	return out, nil
}
