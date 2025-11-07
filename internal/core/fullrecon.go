package core

import (
	"bufio"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// FullRecon builds a ScanContext (legacy helper, no longer used in new external-only design).
// Kept for compatibility; internally memanggil FullReconWithConcurrency.
func FullRecon(targets []Target, useExternal bool, verbose bool) *ScanContext {
	return FullReconWithConcurrency(targets, useExternal, verbose, 10)
}

// FullReconWithConcurrency (legacy) - tidak lagi dipakai sebagai path utama,
// tapi dibiarkan untuk kompatibilitas. Pipeline baru menggunakan helper
// RunDefaultRecon / RunLightExternalRecon / RunAggressiveExternalRecon.
func FullReconWithConcurrency(targets []Target, useExternal bool, verbose bool, concurrency int) *ScanContext {
	if concurrency < 1 {
		concurrency = 1
	}

	ctx := &ScanContext{
		Targets:     targets,
		Concurrency: concurrency,
	}

	// 1) Basic recon (concurrent)
	//    Tetap dilakukan untuk mendapatkan fingerprint dasar.
	ctx.Recon = ReconBasicWithConcurrency(targets, concurrency)

	// 2) URL pool collection
	// Untuk mode agresif (-fa), kita gunakan pipeline eksternal dengan file sementara:
	//   subfinder -d <domain> -t <c> [-silent] -o subs.txt
	//   httpx -l subs.txt -t <c> -mc 200 [-silent] -o httpx.txt
	//   cat httpx.txt | gau --threads <c> > gau.txt
	//   httpx -l gau.txt -t <c> -mc 200 [-silent] -o clean.txt
	// Semua file disimpan di direktori temporary dan dihapus setelah selesai.
	// Jika tool eksternal tidak tersedia / gagal, fallback ke mekanisme internal
	// (crawler + static paths + optional gau in-memory) seperti sebelumnya.
	pool := map[string]struct{}{}

	// Batas dasar untuk jumlah endpoint per target (fallback / non-eksternal)
	baseCrawlLimit := 60
	baseStaticPaths := []string{"/", "/login", "/admin", "/search", "/api", "/dashboard"}

	// Jika useExternal true, target tunggal, dan alat tersedia, coba pipeline agresif temp-file.
	// Pipeline ini hanya dijalankan ketika context agresif diaktifkan oleh caller (-fa).
	if useExternal && len(targets) == 1 && binaryExists("subfinder") && binaryExists("httpx") && binaryExists("gau") && ctx.IsAggressive() {
		t := targets[0]
		domain := normalizeDomainForExternal(t.URL)

		if domain != "" {
			if verbose {
				fmt.Printf("[*] [fa] Using external aggressive pipeline (temp files) for %s\n", domain)
			}

			clean, counts, err := runAggressivePipelineWithTempFiles(domain, concurrency, verbose)
			if err == nil && len(clean) > 0 {
				for _, u := range clean {
					pool[u] = struct{}{}
				}

				if counts.subs > 0 {
					ctx.ExternalUsed = append(ctx.ExternalUsed, "subfinder")
				}
				if counts.httpx1 > 0 || counts.httpx2 > 0 {
					ctx.ExternalUsed = append(ctx.ExternalUsed, "httpx")
				}
				if counts.gau > 0 {
					ctx.ExternalUsed = append(ctx.ExternalUsed, "gau")
				}

				if verbose {
					fmt.Printf("[fa] Summary: subfinder=%d, httpx(subs)=%d, gau=%d, httpx(gau clean)=%d\n",
						counts.subs, counts.httpx1, counts.gau, counts.httpx2)
				} else {
					fmt.Printf("[fa] External pipeline summary: subfinder=%d, httpx(subs)=%d, gau=%d, httpx(clean)=%d\n",
						counts.subs, counts.httpx1, counts.gau, counts.httpx2)
				}

				// Jika pipeline eksternal menghasilkan URL, lanjut ke filter & buckets
				// tanpa fallback internal yang berat.
				if len(pool) > 0 {
					goto BUILD_LIVE_FROM_POOL
				}
			} else if verbose && err != nil {
				fmt.Printf("[fa] External aggressive pipeline failed: %v (falling back to internal)\n", err)
			}
		}
	}

	// Fallback: mekanisme internal (dipakai jika pipeline eksternal tidak tersedia/berhasil)
	for _, t := range targets {
		limit := baseCrawlLimit
		paths := append([]string{}, baseStaticPaths...)

		if concurrency >= 30 {
			limit = baseCrawlLimit * 3
		} else if concurrency >= 20 {
			limit = baseCrawlLimit * 2
		}

		for _, ep := range CrawlBasicWithConcurrency(t, limit, concurrency) {
			pool[ep.URL] = struct{}{}
		}

		if concurrency >= 30 {
			paths = append(paths,
				"/admin/login",
				"/admin-panel",
				"/backup",
				"/backups",
				"/old",
				"/staging",
				"/test",
				"/public",
				"/.git",
				"/.env",
			)
		}

		for _, p := range paths {
			u := strings.TrimRight(t.URL, "/") + p
			pool[u] = struct{}{}
		}

		// Catatan:
		// gau hanya boleh dijalankan dalam konteks pipeline agresif (-fa) setelah httpx dari subfinder.
		// Pemanggilan runURLCollector("gau", ...) di sini di-nonaktifkan agar gau tidak berjalan
		// pada mode default / -F.
		//
		// if useExternal && binaryExists("gau") {
		// 	urls, used := runURLCollector("gau", t, verbose)
		// 	if used {
		// 		ctx.ExternalUsed = append(ctx.ExternalUsed, "gau")
		// 	}
		// 	for _, u := range urls {
		// 		pool[u] = struct{}{}
		// 	}
		// }
	}

	for u := range pool {
		ctx.URLPool = append(ctx.URLPool, u)
	}

BUILD_LIVE_FROM_POOL:
	// 3) Live filter (httpx-like, concurrent)
	ctx.LiveURLs = filterLiveConcurrent(ctx.URLPool, concurrency)

	// 4) Classify parameters (gf-style)
	ctx.Buckets = ClassifyParams(ctx.LiveURLs)

	return ctx
}

// runURLCollector tries external tools like gau/waybackurls.
func runURLCollector(tool string, t Target, verbose bool) ([]string, bool) {
	// Contoh:
	//   gau https://target.com
	//   waybackurls https://target.com
	cmd := exec.Command(tool, t.URL)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		if verbose {
			fmt.Printf("[!] Failed to attach stdout for %s: %v\n", tool, err)
		}
		return nil, false
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		if verbose {
			fmt.Printf("[!] Failed to attach stderr for %s: %v\n", tool, err)
		}
		return nil, false
	}

	if err := cmd.Start(); err != nil {
		if verbose {
			fmt.Printf("[!] Failed to start %s for %s: %v\n", tool, t.URL, err)
		}
		return nil, false
	}

	if verbose {
		fmt.Printf("[ext:%s] started for %s\n", tool, t.URL)
	}

	var urls []string

	// Scanner untuk STDOUT
	stdoutScanner := bufio.NewScanner(stdout)
	go func() {
		for stdoutScanner.Scan() {
			line := strings.TrimSpace(stdoutScanner.Text())
			if line == "" {
				continue
			}
			if verbose {
				// Tampilkan live output tool eksternal
				fmt.Printf("[ext:%s][out] %s\n", tool, line)
			}
			urls = append(urls, line)
		}
	}()

	// Scanner untuk STDERR
	if verbose {
		go func() {
			errScanner := bufio.NewScanner(stderr)
			for errScanner.Scan() {
				line := strings.TrimSpace(errScanner.Text())
				if line == "" {
					continue
				}
				// Tampilkan live error/warning dari tool eksternal
				fmt.Printf("[ext:%s][err] %s\n", tool, line)
			}
		}()
	}

	if err := cmd.Wait(); err != nil && verbose {
		fmt.Printf("[ext:%s] exited with error: %v\n", tool, err)
	}

	if verbose && len(urls) > 0 {
		fmt.Printf("    [%s] collected %d URLs\n", tool, len(urls))
	}
	return urls, len(urls) > 0
}

// filterLive keeps only URLs with "interesting" HTTP status codes (sequential).
// Deprecated in favor of filterLiveConcurrent, but kept for compatibility.
func filterLive(urls []string) []string {
	return filterLiveConcurrent(urls, 10)
}

// filterLiveConcurrent keeps only URLs with "interesting" HTTP status codes,
// using a bounded worker pool controlled by concurrency.
func filterLiveConcurrent(urls []string, concurrency int) []string {
	if concurrency < 1 {
		concurrency = 1
	}

	client := &http.Client{Timeout: 6 * time.Second}
	var live []string
	seen := make(map[string]struct{})
	var mu sync.Mutex
	var wg sync.WaitGroup
	sem := make(chan struct{}, concurrency)

	for _, raw := range urls {
		rawURL := raw

		mu.Lock()
		if _, ok := seen[rawURL]; ok {
			mu.Unlock()
			continue
		}
		seen[rawURL] = struct{}{}
		mu.Unlock()

		wg.Add(1)
		sem <- struct{}{}
		go func() {
			defer wg.Done()
			defer func() { <-sem }()

			u, err := url.Parse(rawURL)
			if err != nil || u.Scheme == "" || u.Host == "" {
				return
			}

			req, _ := http.NewRequest("GET", rawURL, nil)
			req.Header.Set("User-Agent", "autohunt-livecheck/1.0")

			resp, err := client.Do(req)
			if err != nil {
				return
			}
			resp.Body.Close()

			if resp.StatusCode == 200 || resp.StatusCode == 201 || resp.StatusCode == 202 ||
				resp.StatusCode == 301 || resp.StatusCode == 302 || resp.StatusCode == 403 {
				mu.Lock()
				live = append(live, rawURL)
				mu.Unlock()
			}
		}()
	}

	wg.Wait()
	return live
}

// ClassifyParams splits live URLs into vulnerability-specific buckets (SQLi, XSS, LFI, etc).
// It is exported so it can be reused by other packages (e.g. main, modules) when needed.
func ClassifyParams(urls []string) ClassifiedBuckets {
	var buckets ClassifiedBuckets

	for _, raw := range urls {
		u, err := url.Parse(raw)
		if err != nil {
			continue
		}
		q := u.Query()
		if len(q) == 0 {
			continue
		}

		for name := range q {
			lname := strings.ToLower(name)

			ep := EndpointParam{URL: raw, Param: name}

			// sqli
			if containsAny(lname, []string{"id", "uid", "user", "pid", "prod", "item", "cat", "order"}) {
				buckets.SQLi = append(buckets.SQLi, ep)
			}

			// xss
			if containsAny(lname, []string{"q", "query", "search", "message", "comment", "s"}) {
				buckets.XSS = append(buckets.XSS, ep)
			}

			// lfi
			if containsAny(lname, []string{"file", "path", "page", "include", "template", "view"}) {
				buckets.LFI = append(buckets.LFI, ep)
			}

			// open redirect
			if containsAny(lname, []string{"redirect", "url", "next", "return", "goto", "dest"}) {
				buckets.OpenRedirect = append(buckets.OpenRedirect, ep)
			}

			// ssrf
			if containsAny(lname, []string{"url", "dest", "endpoint", "webhook", "callback"}) {
				buckets.SSRF = append(buckets.SSRF, ep)
			}
		}
	}

	return buckets
}

// classifyParams is kept for backward compatibility and delegates to ClassifyParams.
func classifyParams(urls []string) ClassifiedBuckets {
	return ClassifyParams(urls)
}

func containsAny(s string, parts []string) bool {
	for _, p := range parts {
		if strings.Contains(s, p) {
			return true
		}
	}
	return false
}

// ===== Aggressive external helpers for -fa pipeline =====

// binaryExists checks if a binary is available in PATH.
func binaryExists(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

// normalizeDomainForExternal mengekstrak domain dari target URL untuk subfinder/gau.
func normalizeDomainForExternal(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	if u.Host != "" {
		return u.Host
	}
	return strings.TrimSpace(raw)
}

// runSubfinder menjalankan subfinder -d domain dan mengembalikan daftar subdomain mentah.
// Catatan:
// - Fungsi ini tidak lagi meng-chain httpx; dipakai untuk mode in-memory fallback.
// - Untuk pipeline -fa dengan temp-file, gunakan runAggressivePipelineWithTempFiles.
func runSubfinder(domain string, concurrency int, verbose bool) []string {
	if !binaryExists("subfinder") {
		return nil
	}

	var args []string
	if verbose {
		// Verbose: tampilkan output asli subfinder (tanpa -silent)
		args = []string{"-d", domain}
	} else {
		// Non-verbose: gunakan -silent untuk output bersih
		args = []string{"-d", domain, "-silent"}
	}
	if concurrency > 0 {
		args = append(args, "-t", fmt.Sprintf("%d", concurrency))
	}

	cmd := exec.Command("subfinder", args...)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		if verbose {
			fmt.Printf("[subfinder] failed to get stdout: %v\n", err)
		}
		return nil
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		if verbose {
			fmt.Printf("[subfinder] failed to get stderr: %v\n", err)
		}
		return nil
	}

	if err := cmd.Start(); err != nil {
		if verbose {
			fmt.Printf("[subfinder] error: %v\n", err)
		}
		return nil
	}

	var subs []string

	// Tampilkan stderr apa adanya jika verbose
	if verbose {
		go func() {
			sc := bufio.NewScanner(stderr)
			for sc.Scan() {
				line := strings.TrimSpace(sc.Text())
				if line != "" {
					fmt.Println(line)
				}
			}
		}()
	}

	// Baca stdout dan kumpulkan subdomain
	sc := bufio.NewScanner(stdout)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		if verbose {
			fmt.Println(line)
		}
		subs = append(subs, line)
	}

	_ = cmd.Wait()

	if !verbose && len(subs) > 0 {
		fmt.Printf("[subfinder] %d subdomains found\n", len(subs))
	}

	return subs
}

// runHttpxOnList menjalankan httpx pada list host/URL dan mengembalikan hasil dengan status 200 saja.
// - Selalu menggunakan -mc 200.
// - Jika verbose (autohunt -v): tanpa -silent, tampilkan output asli.
// - Jika non-verbose: gunakan -silent dan hanya cetak ringkasan.
func runHttpxOnList(list []string, concurrency int, verbose bool) []string {
	if !binaryExists("httpx") || len(list) == 0 {
		return list
	}

	var args []string
	if verbose {
		args = []string{"-status-code", "-follow-redirects", "-mc", "200"}
	} else {
		args = []string{"-silent", "-status-code", "-follow-redirects", "-mc", "200"}
	}
	if concurrency > 0 {
		args = append(args, "-t", fmt.Sprintf("%d", concurrency))
	}

	cmd := exec.Command("httpx", args...)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return list
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return list
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return list
	}

	if err := cmd.Start(); err != nil {
		return list
	}

	// kirim input list ke httpx
	go func() {
		defer stdin.Close()
		for _, h := range list {
			if strings.TrimSpace(h) != "" {
				fmt.Fprintln(stdin, h)
			}
		}
	}()

	var live []string

	// jika verbose, tampilkan stderr apa adanya
	if verbose {
		go func() {
			sc := bufio.NewScanner(stderr)
			for sc.Scan() {
				line := sc.Text()
				if strings.TrimSpace(line) != "" {
					fmt.Println(line)
				}
			}
		}()
	}

	// baca stdout, tampilkan (verbose) dan simpan
	sc := bufio.NewScanner(stdout)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		if verbose {
			fmt.Println(line)
		}
		live = append(live, line)
	}
	_ = cmd.Wait()

	if !verbose && len(live) > 0 {
		fmt.Printf("[httpx] %d hosts/URLs alive\n", len(live))
	}

	return live
}

// runGauOnList menjalankan gau pada list host/URL dan mengembalikan URL gabungan.
// - Jika verbose: tampilkan output asli gau untuk transparansi.
// - Jika tidak: hanya parsing hasil (seperti sebelumnya).
func runGauOnList(list []string, concurrency int, verbose bool) []string {
	if !binaryExists("gau") || len(list) == 0 {
		return nil
	}
	var urls []string
	for _, base := range list {
		base = strings.TrimSpace(base)
		if base == "" {
			continue
		}
		var args []string
		if concurrency > 0 {
			args = append(args, fmt.Sprintf("--threads=%d", concurrency))
		}
		args = append(args, base)

		cmd := exec.Command("gau", args...)
		stdout, err := cmd.StdoutPipe()
		if err != nil {
			if verbose {
				fmt.Printf("[gau] failed stdout on %s: %v\n", base, err)
			}
			continue
		}
		stderr, err := cmd.StderrPipe()
		if err != nil {
			if verbose {
				fmt.Printf("[gau] failed stderr on %s: %v\n", base, err)
			}
			continue
		}

		if err := cmd.Start(); err != nil {
			if verbose {
				fmt.Printf("[gau] error on %s: %v\n", base, err)
			}
			continue
		}

		// tampilkan stderr jika verbose
		if verbose {
			go func() {
				sc := bufio.NewScanner(stderr)
				for sc.Scan() {
					line := sc.Text()
					if strings.TrimSpace(line) != "" {
						fmt.Printf("[gau][err] %s\n", line)
					}
				}
			}()
		}

		// baca stdout
		sc := bufio.NewScanner(stdout)
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" {
				continue
			}
			if verbose {
				fmt.Printf("[gau][out] %s\n", line)
			}
			urls = append(urls, line)
		}

		_ = cmd.Wait()
	}
	if !verbose && len(urls) > 0 {
		fmt.Printf("[gau] collected %d URLs from live hosts\n", len(urls))
	}
	return urls
}

// runHttpxOnListWithMC menjalankan httpx dengan -mc filter untuk URL final.
// Digunakan oleh pipeline agresif eksternal.
func runHttpxOnListWithMC(list []string, concurrency int, verbose bool) []string {
	if !binaryExists("httpx") || len(list) == 0 {
		return list
	}

	// Untuk filter final, kini hanya gunakan status 200 agar konsisten.
	var args []string
	if verbose {
		args = []string{"-status-code", "-follow-redirects", "-mc", "200"}
	} else {
		args = []string{"-silent", "-status-code", "-follow-redirects", "-mc", "200"}
	}
	if concurrency > 0 {
		args = append(args, "-t", fmt.Sprintf("%d", concurrency))
	}

	cmd := exec.Command("httpx", args...)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return list
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return list
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return list
	}
	if err := cmd.Start(); err != nil {
		return list
	}

	go func() {
		defer stdin.Close()
		for _, u := range list {
			if strings.TrimSpace(u) != "" {
				fmt.Fprintln(stdin, u)
			}
		}
	}()

	var clean []string

	// jika verbose, tampilkan stderr httpx
	if verbose {
		go func() {
			sc := bufio.NewScanner(stderr)
			for sc.Scan() {
				line := sc.Text()
				if strings.TrimSpace(line) != "" {
					fmt.Println(line)
				}
			}
		}()
	}

	// baca stdout, tampilkan jika verbose dan simpan
	sc := bufio.NewScanner(stdout)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		if verbose {
			fmt.Println(line)
		}
		clean = append(clean, line)
	}
	_ = cmd.Wait()

	if !verbose && len(clean) > 0 {
		fmt.Printf("[httpx] %d URLs after mc filter\n", len(clean))
	}
	return clean
}

// aggressivePipelineCounts menyimpan metrik ringkas untuk pipeline -fa.
type aggressivePipelineCounts struct {
	subs   int
	httpx1 int
	gau    int
	httpx2 int
}

// runAggressivePipelineWithTempFiles menjalankan rantai agresif:
// subfinder -> httpx -> gau -> httpx menggunakan file sementara.
// - Menghormati verbose:
//   - verbose=true  : tools tanpa -silent, output live.
//   - verbose=false : tools dengan -silent (jika mendukung), hanya ringkasan.
//
// - Mengembalikan daftar URL final (mc 200) + metrik per tahap.
func runAggressivePipelineWithTempFiles(domain string, concurrency int, verbose bool) ([]string, aggressivePipelineCounts, error) {
	counts := aggressivePipelineCounts{}

	// Buat direktori temp khusus pipeline ini
	tmpDir, err := os.MkdirTemp("", "autohunt-fa-*")
	if err != nil {
		return nil, counts, fmt.Errorf("failed to create temp dir: %w", err)
	}
	// Pastikan dibersihkan setelah selesai
	defer os.RemoveAll(tmpDir)

	subsPath := filepath.Join(tmpDir, "subs.txt")
	httpxSubsPath := filepath.Join(tmpDir, "httpx.txt")
	gauPath := filepath.Join(tmpDir, "gau.txt")
	cleanPath := filepath.Join(tmpDir, "clean.txt")

	// 1) subfinder -d domain -t <c> [-silent] -o subs.txt
	{
		args := []string{"-d", domain, "-t", fmt.Sprintf("%d", concurrency), "-o", subsPath}
		if !verbose {
			args = append(args, "-silent")
		}
		if verbose {
			fmt.Printf("[fa] Running: subfinder %s\n", strings.Join(args, " "))
		}
		cmd := exec.Command("subfinder", args...)
		out, err := cmd.CombinedOutput()
		if verbose && len(out) > 0 {
			fmt.Print(string(out))
		}
		if err != nil {
			return nil, counts, fmt.Errorf("subfinder failed: %w", err)
		}
		data, _ := os.ReadFile(subsPath)
		if len(data) == 0 {
			return nil, counts, fmt.Errorf("subfinder produced no results")
		}
		counts.subs = len(strings.Split(strings.TrimSpace(string(data)), "\n"))
		if !verbose {
			fmt.Printf("[fa] subfinder: %d subdomains\n", counts.subs)
		}
	}

	// 2) httpx -l subs.txt -mc 200 -t <c> [-silent] -o httpx.txt
	{
		args := []string{"-l", subsPath, "-mc", "200", "-t", fmt.Sprintf("%d", concurrency), "-o", httpxSubsPath}
		if !verbose {
			args = append(args, "-silent")
		}
		if verbose {
			fmt.Printf("[fa] Running: httpx %s\n", strings.Join(args, " "))
		}
		cmd := exec.Command("httpx", args...)
		out, err := cmd.CombinedOutput()
		if verbose && len(out) > 0 {
			fmt.Print(string(out))
		}
		if err != nil {
			return nil, counts, fmt.Errorf("httpx(subs) failed: %w", err)
		}
		data, _ := os.ReadFile(httpxSubsPath)
		if len(data) == 0 {
			return nil, counts, fmt.Errorf("httpx(subs) produced no results")
		}
		counts.httpx1 = len(strings.Split(strings.TrimSpace(string(data)), "\n"))
		if !verbose {
			fmt.Printf("[fa] httpx(subs): %d live hosts (mc=200)\n", counts.httpx1)
		}
	}

	// 3) cat httpx.txt | gau --threads <c> > gau.txt
	{
		httpxData, err := os.ReadFile(httpxSubsPath)
		if err != nil {
			return nil, counts, fmt.Errorf("read httpx(subs) failed: %w", err)
		}
		lines := strings.Split(strings.TrimSpace(string(httpxData)), "\n")
		gauFile, err := os.Create(gauPath)
		if err != nil {
			return nil, counts, fmt.Errorf("create gau.txt failed: %w", err)
		}
		defer gauFile.Close()

		if verbose {
			fmt.Printf("[fa] Running: gau --threads=%d (piped from httpx(subs))\n", concurrency)
		}

		for _, host := range lines {
			host = strings.TrimSpace(host)
			if host == "" {
				continue
			}
			args := []string{fmt.Sprintf("--threads=%d", concurrency), host}
			cmd := exec.Command("gau", args...)
			out, err := cmd.Output()
			if verbose && len(out) > 0 {
				for _, l := range strings.Split(strings.TrimSpace(string(out)), "\n") {
					if l != "" {
						fmt.Printf("[gau] %s\n", l)
					}
				}
			}
			if err != nil {
				if verbose {
					fmt.Printf("[fa] gau failed for %s: %v\n", host, err)
				}
				continue
			}
			if len(out) > 0 {
				if _, werr := gauFile.Write(out); werr != nil {
					return nil, counts, fmt.Errorf("write gau.txt failed: %w", werr)
				}
				if !strings.HasSuffix(string(out), "\n") {
					_, _ = gauFile.WriteString("\n")
				}
			}
		}

		gauData, _ := os.ReadFile(gauPath)
		if len(gauData) == 0 {
			return nil, counts, fmt.Errorf("gau produced no URLs")
		}
		counts.gau = len(strings.Split(strings.TrimSpace(string(gauData)), "\n"))
		if !verbose {
			fmt.Printf("[fa] gau: %d URLs\n", counts.gau)
		}
	}

	// 4) httpx -l gau.txt -mc 200 -t <c> [-silent] -o clean.txt
	{
		args := []string{"-l", gauPath, "-mc", "200", "-t", fmt.Sprintf("%d", concurrency), "-o", cleanPath}
		if !verbose {
			args = append(args, "-silent")
		}
		if verbose {
			fmt.Printf("[fa] Running: httpx %s\n", strings.Join(args, " "))
		}
		cmd := exec.Command("httpx", args...)
		out, err := cmd.CombinedOutput()
		if verbose && len(out) > 0 {
			fmt.Print(string(out))
		}
		if err != nil {
			return nil, counts, fmt.Errorf("httpx(gau) failed: %w", err)
		}
		cleanData, _ := os.ReadFile(cleanPath)
		if len(cleanData) == 0 {
			return nil, counts, fmt.Errorf("httpx(gau) produced no clean URLs")
		}
		lines := strings.Split(strings.TrimSpace(string(cleanData)), "\n")
		counts.httpx2 = len(lines)
		if !verbose {
			fmt.Printf("[fa] httpx(clean): %d URLs (mc=200)\n", counts.httpx2)
		}
		return lines, counts, nil
	}
}
