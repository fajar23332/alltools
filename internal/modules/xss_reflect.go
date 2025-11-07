package modules

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"autohunt/internal/core"
)

// XSSReflectModule is a more powerful reflected-XSS detector.
// It uses the crawler to discover multiple endpoints, then injects payloads
// into discovered query parameters and checks for reflection patterns.
//
// Design goals:
// - Safe: only uses lightweight GET requests with benign payloads.
// - Useful: scans multiple endpoints instead of just the root.
// - Fast: limited endpoints per target to avoid brute-force or abuse.
type XSSReflectModule struct {
	maxEndpointsPerTarget int
	client                *http.Client
	// You can extend with more payloads or context-aware patterns.
	payload string
}

func NewXSSReflectModule() *XSSReflectModule {
	return &XSSReflectModule{
		maxEndpointsPerTarget: 40,
		client: &http.Client{
			Timeout: 8 * time.Second,
		},
		payload: `autohunt_xss_probe_<>"'</script>`,
	}
}

func (m *XSSReflectModule) Name() string {
	return "XSSReflect"
}

func (m *XSSReflectModule) Run(targets []core.Target) ([]core.Finding, error) {
	var findings []core.Finding

	for _, t := range targets {
		endpoints := core.CrawlBasic(t, m.maxEndpointsPerTarget)
		if len(endpoints) == 0 {
			// Fallback: at least test the root with a generic param
			endpoints = append(endpoints, core.CrawledEndpoint{
				URL:    t.URL,
				Params: []string{"q"},
			})
		}

		for _, ep := range endpoints {
			// If no params found, try a generic "q" param.
			params := ep.Params
			if len(params) == 0 {
				params = []string{"q"}
			}

			for _, p := range params {
				testURL, ok := injectXSSPayload(ep.URL, p, m.payload)
				if !ok {
					continue
				}

				body, err := m.httpGetBody(testURL)
				if err != nil || body == "" {
					continue
				}

				if isReflectedXSS(body, m.payload) {
					findings = append(findings, core.Finding{
						Target:     t.URL,
						Endpoint:   testURL,
						Module:     m.Name(),
						Type:       "Possible Reflected XSS",
						Severity:   "Medium",
						Confidence: 0.78,
						Evidence:   fmt.Sprintf("Payload reflected via param '%s'", p),
						Tags:       []string{"xss", "reflected"},
					})
				}
			}
		}
	}

	return findings, nil
}

// XSSReflectContextModule is the ScanContext-based implementation.
// It leverages FullRecon buckets (gf-style) for targeted XSS testing:
// - Uses ctx.Buckets.XSS when available
// - Falls back to ctx.LiveURLs and generic params when buckets are empty
type XSSReflectContextModule struct {
	client  *http.Client
	payload string
}

func NewXSSReflectContextModule() *XSSReflectContextModule {
	return &XSSReflectContextModule{
		client: &http.Client{
			Timeout: 8 * time.Second,
		},
		// Payload dasar: unik, mudah dilacak, tidak merusak.
		payload: `autohunt_xss_probe_<>"'</script>`,
	}
}

func (m *XSSReflectContextModule) Name() string {
	return "XSSReflect"
}

func (m *XSSReflectContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	var findings []core.Finding

	if ctx == nil {
		return nil, nil
	}

	// Bangun daftar payload:
	// - Selalu gunakan payload utama.
	// - Jika aggressive, tambahkan payload ekstra dari wordlists/xss_payloads.txt (jika ada).
	payloads := []string{m.payload}
	if ctx.IsAggressive() {
		if extra := loadXSSPayloadsFromWordlist("wordlists/xss_payloads.txt", 5); len(extra) > 0 {
			payloads = append(payloads, extra...)
		}
	}

	// Prefer focused XSS bucket dari FullRecon
	if len(ctx.Buckets.XSS) > 0 {
		for _, ep := range ctx.Buckets.XSS {
			for _, pl := range payloads {
				testURL, ok := injectXSSPayload(ep.URL, ep.Param, pl)
				if !ok {
					continue
				}

				body, err := m.httpGetBody(testURL)
				if err != nil || body == "" {
					continue
				}

				if isReflectedXSS(body, pl) {
					findings = append(findings, core.Finding{
						Target:     deriveTargetForURL(ctx, ep.URL),
						Endpoint:   testURL,
						Module:     m.Name(),
						Type:       "Possible Reflected XSS",
						Severity:   "Medium",
						Confidence: 0.85,
						Evidence:   fmt.Sprintf("Payload reflected via param '%s' (bucketed)", ep.Param),
						Tags:       []string{"xss", "reflected", "bucket:xss"},
					})
					// Satu hit per param/endpoint sudah cukup untuk menghindari spam.
					break
				}
			}
		}
		return findings, nil
	}

	// Fallback: gunakan LiveURLs sebagai kandidat XSS generic
	for _, raw := range ctx.LiveURLs {
		u, err := url.Parse(raw)
		if err != nil {
			continue
		}
		q := u.Query()

		// Jika tidak ada parameter, coba param generic "q"
		if len(q) == 0 {
			for _, pl := range payloads {
				testURL, ok := injectXSSPayload(raw, "q", pl)
				if !ok {
					continue
				}
				body, err := m.httpGetBody(testURL)
				if err != nil || body == "" {
					continue
				}
				if isReflectedXSS(body, pl) {
					findings = append(findings, core.Finding{
						Target:     deriveTargetForURL(ctx, raw),
						Endpoint:   testURL,
						Module:     m.Name(),
						Type:       "Possible Reflected XSS",
						Severity:   "Medium",
						Confidence: 0.72,
						Evidence:   "Payload reflected via generic param 'q' (fallback)",
						Tags:       []string{"xss", "reflected", "fallback"},
					})
					break
				}
			}
			continue
		}

		// Jika ada parameter, uji tiap param dengan payload terpilih
		for name := range q {
			for _, pl := range payloads {
				testURL, ok := injectXSSPayload(raw, name, pl)
				if !ok {
					continue
				}
				body, err := m.httpGetBody(testURL)
				if err != nil || body == "" {
					continue
				}
				if isReflectedXSS(body, pl) {
					findings = append(findings, core.Finding{
						Target:     deriveTargetForURL(ctx, raw),
						Endpoint:   testURL,
						Module:     m.Name(),
						Type:       "Possible Reflected XSS",
						Severity:   "Medium",
						Confidence: 0.78,
						Evidence:   fmt.Sprintf("Payload reflected via param '%s' (liveurls fallback)", name),
						Tags:       []string{"xss", "reflected", "liveurls"},
					})
					// Hindari spam di param yang sama.
					break
				}
			}
		}
	}

	return findings, nil
}

// httpGetBody wraps GET requests with the XSSReflectContextModule's HTTP client.
func (m *XSSReflectContextModule) httpGetBody(u string) (string, error) {
	resp, err := m.client.Get(u)
	if err != nil {
		return "", err
	}
	if resp.Body == nil {
		return "", nil
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// deriveTargetForURL maps a concrete URL back to a logical target base from ScanContext.
// This helper is defined once centrally for XSS/SQLi/LFI/OpenRedirect/SSRF context usage.
func deriveTargetForURL(ctx *core.ScanContext, raw string) string {
	if ctx == nil {
		return raw
	}
	for _, t := range ctx.Targets {
		if strings.Contains(raw, t.URL) {
			return t.URL
		}
	}
	return raw
}

// injectXSSPayload takes a base URL and sets/replaces a specific query parameter with the payload.
func injectXSSPayload(rawURL, param, payload string) (string, bool) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return "", false
	}

	q := u.Query()
	// Only overwrite if param is meaningful or already exists; but for coverage,
	// we also allow creating it when scanning.
	q.Set(param, payload)
	u.RawQuery = q.Encode()

	return u.String(), true
}

// httpGetBody wraps GET requests with the module's client.
func (m *XSSReflectModule) httpGetBody(u string) (string, error) {
	resp, err := m.client.Get(u)
	if err != nil {
		return "", err
	}
	if resp.Body == nil {
		return "", nil
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// isReflectedXSS applies simple but stronger heuristics to confirm a potential reflected XSS:
// - Checks if the raw payload is reflected
// - Also checks for HTML-encoded or partially encoded variants
// - Keeps it lightweight: no complex JS execution, only response-body analysis.
func isReflectedXSS(body, payload string) bool {
	if body == "" {
		return false
	}

	// Direct reflection
	if strings.Contains(body, payload) {
		return true
	}

	lower := strings.ToLower(body)
	lp := strings.ToLower(payload)

	// Check for common encodings/transformations (very simple heuristics)
	encodedVariants := []string{
		strings.ReplaceAll(lp, "<", "&lt;"),
		strings.ReplaceAll(lp, ">", "&gt;"),
		strings.ReplaceAll(lp, `"`, "&quot;"),
		strings.ReplaceAll(lp, `"`, "&#34;"),
		strings.ReplaceAll(lp, "'", "&#39;"),
	}

	for _, ev := range encodedVariants {
		if ev != "" && strings.Contains(lower, ev) {
			return true
		}
	}

	return false
}

// loadXSSPayloadsFromWordlist loads additional XSS payloads from a wordlist file (if present),
// limiting to maxCount entries to keep aggressive mode brutal but controlled.
func loadXSSPayloadsFromWordlist(path string, maxCount int) []string {
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
		if maxCount > 0 && len(out) >= maxCount {
			break
		}
	}
	return out
}
