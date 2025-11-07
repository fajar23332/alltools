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
	ctx.Recon = ReconBasicWithConcurrency(targets, concurrency)

	// 2) URL pool collection (gunakan Aggressive flag untuk atur kedalaman)
	pool := map[string]struct{}{}

	// Batas dasar untuk jumlah endpoint per target
	baseCrawlLimit := 60
	baseStaticPaths := []string{"/", "/login", "/admin", "/search", "/api", "/dashboard"}

	for _, t := range targets {
		limit := baseCrawlLimit
		paths := append([]string{}, baseStaticPaths...)

		// Jika Aggressive diaktifkan oleh caller, perluas cakupan secara terkontrol:
		// - Tambah limit crawl
		// - Tambah beberapa static paths umum
		// Catatan: ctx.Aggressive akan di-set oleh pemanggil segera setelah FullRecon selesai.
		if concurrency >= 30 {
			limit = baseCrawlLimit * 3
		} else if concurrency >= 20 {
			limit = baseCrawlLimit * 2
		}

		// Crawl internal dengan limit yang sudah ditentukan
		for _, ep := range CrawlBasicWithConcurrency(t, limit, concurrency) {
			pool[ep.URL] = struct{}{}
		}

		// Jika mode agresif, tambahkan beberapa path umum ekstra
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

		if useExternal {
			// waybackurls / gau style
			for _, ext := range []string{"gau", "waybackurls"} {
				urls, used := runURLCollector(ext, t, verbose)
				if used {
					ctx.ExternalUsed = append(ctx.ExternalUsed, ext)
				}
				for _, u := range urls {
					pool[u] = struct{}{}
				}
			}
		}
	}

	for u := range pool {
		ctx.URLPool = append(ctx.URLPool, u)
	}

	// 3) Live filter (httpx-like, concurrent)
	ctx.LiveURLs = filterLiveConcurrent(ctx.URLPool, concurrency)

	// 4) Classify parameters (gf-like)
	ctx.Buckets = ClassifyParams(ctx.LiveURLs)

	return ctx
}

// runURLCollector tries external tools like gau/waybackurls.
func runURLCollector(tool string, t Target, verbose bool) ([]string, bool) {
	cmd := exec.Command(tool, t.URL)
	out, err := cmd.StdoutPipe()
	if err != nil {
		return nil, false
	}
	if err := cmd.Start(); err != nil {
		return nil, false
	}

	var urls []string
	sc := bufio.NewScanner(out)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line != "" {
			urls = append(urls, line)
		}
	}
	cmd.Wait()

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
