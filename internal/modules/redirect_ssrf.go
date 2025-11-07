package modules

import (
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"autohunt/internal/core"
)

// OpenRedirectContextModule
//
// Tujuan:
//   - Mendeteksi indikasi Open Redirect berbasis parameter yang sudah
//     diklasifikasi ke dalam ctx.Buckets.OpenRedirect oleh FullRecon.
//
// Cara kerja:
// - Untuk setiap (URL, Param) di bucket OpenRedirect:
//   - Set nilai param menjadi URL eksternal terkontrol (misal https://example.org).
//   - Kirim request (GET) dan periksa:
//   - Apakah Location header atau final URL mengarah ke domain luar tersebut.
//
// - Jika ya, tandai sebagai "Possible Open Redirect".
//
// Catatan:
// - Modul ini tidak berusaha melakukan eksploitasi kompleks, hanya mendeteksi pola redirect keluar.
type OpenRedirectContextModule struct {
	client      *http.Client
	testTargets []string
}

func NewOpenRedirectContextModule() *OpenRedirectContextModule {
	return &OpenRedirectContextModule{
		client: &http.Client{
			Timeout: 8 * time.Second,
			// Redirect akan di-handle manual via CheckRedirect jika ingin.
		},
		// Beberapa target eksternal aman untuk deteksi.
		testTargets: []string{
			"https://example.org",
			"https://example.com",
		},
	}
}

func (m *OpenRedirectContextModule) Name() string {
	return "OpenRedirect"
}

func (m *OpenRedirectContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	var findings []core.Finding
	if ctx == nil || len(ctx.Buckets.OpenRedirect) == 0 {
		return findings, nil
	}

	seen := make(map[string]struct{})
	concurrency := ctx.GetConcurrency()
	if concurrency < 1 {
		concurrency = 1
	}

	type task struct {
		EP core.EndpointParam
	}
	tasks := make(chan task, len(ctx.Buckets.OpenRedirect))
	results := make(chan *core.Finding, len(ctx.Buckets.OpenRedirect))

	// Worker pool
	for i := 0; i < concurrency; i++ {
		go func() {
			for t := range tasks {
				f := m.checkOpenRedirect(ctx, t.EP)
				if f != nil {
					results <- f
				}
			}
		}()
	}

	for _, ep := range ctx.Buckets.OpenRedirect {
		key := ep.URL + "|" + ep.Param
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		tasks <- task{EP: ep}
	}
	close(tasks)

	for range seen {
		select {
		case f := <-results:
			if f != nil {
				findings = append(findings, *f)
			}
		default:
			// no more results
		}
	}

	return findings, nil
}

func (m *OpenRedirectContextModule) checkOpenRedirect(ctx *core.ScanContext, ep core.EndpointParam) *core.Finding {
	u, err := url.Parse(ep.URL)
	if err != nil {
		return nil
	}

	for _, target := range m.testTargets {
		testURL := cloneURLWithParam(u, ep.Param, target)
		if testURL == "" {
			continue
		}

		// Follow redirects manually with limit
		finalURL, locHeader, err := m.followOnce(testURL)
		if err != nil {
			continue
		}

		if isExternalRedirect(target, finalURL, locHeader) {
			return &core.Finding{
				Target:     deriveTargetForURL(ctx, ep.URL),
				Endpoint:   testURL,
				Module:     m.Name(),
				Type:       "Possible Open Redirect",
				Severity:   "Medium",
				Confidence: 0.82,
				Evidence:   fmt.Sprintf("Parameter '%s' appears to redirect to external domain: %s", ep.Param, finalURL),
				Tags:       []string{"open-redirect", "redirect", "bucket:open_redirect"},
			}
		}
	}

	return nil
}

func (m *OpenRedirectContextModule) followOnce(raw string) (finalURL string, locHeader string, err error) {
	req, err := http.NewRequest("GET", raw, nil)
	if err != nil {
		return "", "", err
	}
	req.Header.Set("User-Agent", "autohunt-openredirect/1.0")

	// Custom client to capture single redirect step
	client := &http.Client{
		Timeout: m.client.Timeout,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			// Stop after first redirect
			return http.ErrUseLastResponse
		},
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()

	loc := resp.Header.Get("Location")
	if loc != "" {
		return resolveURL(raw, loc), loc, nil
	}

	return raw, "", nil
}

func resolveURL(baseRaw, loc string) string {
	loc = strings.TrimSpace(loc)
	if loc == "" {
		return baseRaw
	}
	u, err := url.Parse(loc)
	if err == nil && u.IsAbs() {
		return u.String()
	}
	base, err := url.Parse(baseRaw)
	if err != nil {
		return baseRaw
	}
	return base.ResolveReference(u).String()
}

func isExternalRedirect(expectedExternal, finalURL, locHeader string) bool {
	if finalURL == "" {
		return false
	}
	lFinal := strings.ToLower(finalURL)
	lExpected := strings.ToLower(expectedExternal)

	// simple contains/host match
	if strings.Contains(lFinal, lExpected) {
		return true
	}
	if locHeader != "" && strings.Contains(strings.ToLower(locHeader), lExpected) {
		return true
	}
	return false
}

func cloneURLWithParam(u *url.URL, param, value string) string {
	if u == nil {
		return ""
	}
	q := u.Query()
	q.Set(param, value)
	u2 := *u
	u2.RawQuery = q.Encode()
	return u2.String()
}

// deriveTargetForURL helper is defined in another module and reused there to avoid duplication.

// SSRFContextModule
//
// Tujuan:
// - Mendeteksi indikasi parameter SSRF-prone (bukan eksploit penuh).
//
// Cara kerja aman (non-destructive):
// - Untuk setiap (URL, Param) di bucket SSRF:
//   - Set value ke beberapa URL "dummy" yang:
//   - Tidak sensitif
//   - Dapat memicu perilaku berbeda jika server melakukan request keluar (namun di sini kita hanya melihat respon server).
//
// - Heuristik:
//   - Jika respon berubah signifikan atau error spesifik muncul, flag sebagai "Possible SSRF parameter".
//
// - Modul ini TIDAK melakukan DNS callback atau external log server (itu opsional dan sensitif).
type SSRFContextModule struct {
	client  *http.Client
	payload []string
}

func NewSSRFContextModule() *SSRFContextModule {
	return &SSRFContextModule{
		client: &http.Client{
			Timeout: 8 * time.Second,
		},
		// URL dummy aman; dalam implementasi lanjutan bisa diarahkan ke endpoint kontrol user.
		payload: []string{
			"http://127.0.0.1/",
			"http://localhost/",
			"http://0.0.0.0/",
		},
	}
}

func (m *SSRFContextModule) Name() string {
	return "SSRFHeuristics"
}

func (m *SSRFContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	var findings []core.Finding
	if ctx == nil || len(ctx.Buckets.SSRF) == 0 {
		return findings, nil
	}

	concurrency := ctx.GetConcurrency()
	if concurrency < 1 {
		concurrency = 1
	}

	// Jika mode agresif aktif, coba sinkronkan payload dari wordlists/ssrf_targets.txt (jika ada).
	// Ini menambah variasi payload dengan tetap aman dan terkontrol.
	payloads := append([]string{}, m.payload...)
	if ctx.IsAggressive() {
		if extra := loadLinesIfExists("wordlists/ssrf_targets.txt"); len(extra) > 0 {
			payloads = uniqueAppend(payloads, extra)
		}
	}

	type task struct {
		EP core.EndpointParam
	}
	tasks := make(chan task, len(ctx.Buckets.SSRF))
	results := make(chan *core.Finding, len(ctx.Buckets.SSRF))

	// Worker pool
	for i := 0; i < concurrency; i++ {
		go func() {
			for t := range tasks {
				f := m.checkSSRFHeuristic(ctx, t.EP, payloads)
				if f != nil {
					results <- f
				}
			}
		}()
	}

	seen := make(map[string]struct{})
	for _, ep := range ctx.Buckets.SSRF {
		key := ep.URL + "|" + ep.Param
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		tasks <- task{EP: ep}
	}
	close(tasks)

	for range seen {
		select {
		case f := <-results:
			if f != nil {
				findings = append(findings, *f)
			}
		default:
			// no more
		}
	}

	return findings, nil
}

func (m *SSRFContextModule) checkSSRFHeuristic(ctx *core.ScanContext, ep core.EndpointParam, payloads []string) *core.Finding {
	base, err := url.Parse(ep.URL)
	if err != nil {
		return nil
	}

	// baseline
	baselineStatus, _ := m.fetchStatus(ep.URL)

	maxAttempts := 3
	if ctx.IsAggressive() {
		// Dalam mode agresif, izinkan sedikit lebih banyak percobaan aman.
		maxAttempts = 6
	}

	attempts := 0
	for _, p := range payloads {
		if attempts >= maxAttempts {
			break
		}
		attempts++

		testURL := cloneURLWithParam(base, ep.Param, p)
		if testURL == "" {
			continue
		}
		code, bodySnippet := m.fetchStatus(testURL)
		if code == 0 {
			continue
		}

		// Heuristik sangat sederhana:
		// - Jika baseline 2xx dan setelah inject berubah drastis ke 5xx atau error spesifik,
		//   ada indikasi parameter diproses secara SSRF-like.
		if isPotentialSSRFChange(baselineStatus, code, bodySnippet) {
			return &core.Finding{
				Target:     deriveTargetForURL(ctx, ep.URL),
				Endpoint:   testURL,
				Module:     m.Name(),
				Type:       "Possible SSRF parameter (heuristic)",
				Severity:   "Medium",
				Confidence: 0.6,
				Evidence:   fmt.Sprintf("Param '%s' shows SSRF-like behavior with payload '%s'", ep.Param, p),
				Tags:       []string{"ssrf", "heuristic", "bucket:ssrf"},
			}
		}
	}

	return nil
}

func (m *SSRFContextModule) fetchStatus(raw string) (int, string) {
	req, err := http.NewRequest("GET", raw, nil)
	if err != nil {
		return 0, ""
	}
	req.Header.Set("User-Agent", "autohunt-ssrf/1.0")

	resp, err := m.client.Do(req)
	if err != nil || resp == nil {
		return 0, ""
	}
	defer resp.Body.Close()

	// Baca sedikit body untuk pola error (tidak seluruhnya).
	buf := make([]byte, 512)
	n, _ := resp.Body.Read(buf)
	snippet := strings.ToLower(string(buf[:n]))

	return resp.StatusCode, snippet
}

// isPotentialSSRFChange memeriksa perubahan respon yang mencurigakan.
func isPotentialSSRFChange(baseCode, testCode int, bodySnippet string) bool {
	if baseCode == 0 || testCode == 0 {
		return false
	}
	// dari 2xx ke 5xx dengan konten error jaringan/internal
	if baseCode >= 200 && baseCode < 300 && testCode >= 500 {
		if strings.Contains(bodySnippet, "connection refused") ||
			strings.Contains(bodySnippet, "timed out") ||
			strings.Contains(bodySnippet, "unreachable") ||
			strings.Contains(bodySnippet, "cannot resolve") {
			return true
		}
	}
	return false
}

// loadLinesIfExists membaca file baris-per-baris jika ada.
// Jika file tidak ada atau gagal dibaca, mengembalikan slice kosong.
func loadLinesIfExists(path string) []string {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	lines := strings.Split(string(data), "\n")
	var out []string
	for _, l := range lines {
		l = strings.TrimSpace(l)
		if l == "" || strings.HasPrefix(l, "#") {
			continue
		}
		out = append(out, l)
	}
	return out
}

// uniqueAppend menambahkan elemen-elemen baru ke base, menghindari duplikasi.
func uniqueAppend(base []string, extra []string) []string {
	exists := make(map[string]struct{}, len(base))
	for _, b := range base {
		exists[b] = struct{}{}
	}
	for _, e := range extra {
		if _, ok := exists[e]; ok {
			continue
		}
		base = append(base, e)
		exists[e] = struct{}{}
	}
	return base
}
