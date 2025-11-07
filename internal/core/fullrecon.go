package core

import (
	"bufio"
	"fmt"
	"net/http"
	"net/url"
	"os/exec"
	"strings"
	"sync"
	"time"
)

// FullRecon builds a ScanContext (sequential wrapper).
// Prefer FullReconWithConcurrency for better performance.
func FullRecon(targets []Target, useExternal bool, verbose bool) *ScanContext {
	return FullReconWithConcurrency(targets, useExternal, verbose, 10)
}

// FullReconWithConcurrency builds a ScanContext with a bounded worker pool:
// - Runs basic recon (concurrent)
// - Collects URLs (internal + optional external tools)
// - Filters live URLs (httpx-like) concurrently
// - Classifies parameters into buckets (gf-like)
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
	// Untuk mode agresif (ScanContext.Aggressive akan di-set oleh caller setelah ini),
	// kita mencoba menjalankan pipeline eksternal:
	//
	// subfinder -d target -> httpx (live hosts) -> gau (URLs) -> httpx filter (final URLs)
	//
	// Jika tool eksternal tidak tersedia atau gagal, fallback ke mekanisme internal
	// (crawler + static paths + optional gau) seperti sebelumnya.
	pool := map[string]struct{}{}

	// Batas dasar untuk jumlah endpoint per target (fallback / non-eksternal)
	baseCrawlLimit := 60
	baseStaticPaths := []string{"/", "/login", "/admin", "/search", "/api", "/dashboard"}

	// Jika useExternal true dan alat tersedia, coba pipeline agresif:
	// subfinder -> httpx -> gau -> httpx
	if useExternal && len(targets) == 1 && binaryExists("subfinder") && binaryExists("httpx") {
		t := targets[0]
		domain := normalizeDomainForExternal(t.URL)

		if domain != "" {
			if verbose {
				fmt.Printf("[*] [fa] Using external aggressive pipeline for %s\n", domain)
			}

			// 2.1 subfinder -d domain -silent
			subs := runSubfinder(domain, concurrency, verbose)

			// 2.2 httpx on subfinder output (live hosts/URLs)
			liveFromSubs := runHttpxOnList(subs, concurrency, verbose)

			// 2.3 gau on live hosts/URLs (historical URLs)
			gauURLs := runGauOnList(liveFromSubs, concurrency, verbose)

			// 2.4 httpx filter on gau URLs (final clean URLs)
			clean := runHttpxOnListWithMC(gauURLs, concurrency, verbose)

			for _, u := range clean {
				pool[u] = struct{}{}
			}

			// Tandai alat eksternal yang digunakan
			if len(subs) > 0 {
				ctx.ExternalUsed = append(ctx.ExternalUsed, "subfinder")
			}
			if len(liveFromSubs) > 0 {
				ctx.ExternalUsed = append(ctx.ExternalUsed, "httpx")
			}
			if len(gauURLs) > 0 && binaryExists("gau") {
				ctx.ExternalUsed = append(ctx.ExternalUsed, "gau")
			}

			// Jika pipeline eksternal menghasilkan URL, lanjut ke filter & buckets
			// tanpa fallback internal yang berat.
			if len(pool) > 0 {
				goto BUILD_LIVE_FROM_POOL
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

		if useExternal && binaryExists("gau") {
			urls, used := runURLCollector("gau", t, verbose)
			if used {
				ctx.ExternalUsed = append(ctx.ExternalUsed, "gau")
			}
			for _, u := range urls {
				pool[u] = struct{}{}
			}
		}
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

// runSubfinder menjalankan subfinder -d domain.
// Perilaku:
// - Jika verbose == true  -> tampilkan output asli subfinder (tanpa -silent).
// - Jika verbose == false -> gunakan -silent, hanya kumpulkan hasil.
func runSubfinder(domain string, concurrency int, verbose bool) []string {
	if !binaryExists("subfinder") {
		return nil
	}

	var args []string
	if verbose {
		// Tampilkan output asli subfinder
		args = []string{"-d", domain}
	} else {
		// Mode normal: hanya ambil hasil bersih
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
				line := sc.Text()
				if strings.TrimSpace(line) != "" {
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
			// subfinder full output sudah termasuk banner/log/result,
			// jadi langsung tampilkan apa adanya.
			fmt.Println(line)
		}
		// tetap kumpulkan sebagai subdomain candidate
		subs = append(subs, line)
	}

	_ = cmd.Wait()

	if !verbose && len(subs) > 0 {
		fmt.Printf("[subfinder] %d subdomains found\n", len(subs))
	}

	return subs
}

// runHttpxOnList menjalankan httpx pada list host/URL dan mengembalikan hasil live.
// - Jika verbose: tampilkan output asli httpx (tanpa -silent).
// - Jika tidak: gunakan -silent dan hanya parsing hasil.
func runHttpxOnList(list []string, concurrency int, verbose bool) []string {
	if !binaryExists("httpx") || len(list) == 0 {
		return list
	}

	var args []string
	if verbose {
		// Live output: jangan pakai -silent, tapi tetap gunakan -status-code dan -mc 200
		args = []string{"-status-code", "-follow-redirects", "-mc", "200"}
	} else {
		// Non-verbose: tetap sunyi, tapi pastikan hanya status 200 yang digunakan sebagai sumber
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
// - Jika verbose: tampilkan output asli httpx (tanpa -silent).
// - Jika tidak: gunakan -silent dan hanya parsing hasil.
func runHttpxOnListWithMC(list []string, concurrency int, verbose bool) []string {
	if !binaryExists("httpx") || len(list) == 0 {
		return list
	}

	// Untuk filter final, tetap gunakan range status penting (200,204,301,302,307,401,403).
	// Ini sudah termasuk 200 dan digunakan khusus pada tahap akhir.
	var args []string
	if verbose {
		args = []string{"-status-code", "-follow-redirects", "-mc", "200,204,301,302,307,401,403"}
	} else {
		args = []string{"-silent", "-status-code", "-follow-redirects", "-mc", "200,204,301,302,307,401,403"}
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
