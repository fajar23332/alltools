package modules

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"autohunt/internal/core"
)

// SQLiErrorContextModule is a ScanContext-based SQL injection detector.
//
// Tujuan:
// - Menggunakan intelligence dari FullRecon (ctx.Buckets.SQLi, ctx.LiveURLs).
// - Menyerang hanya parameter yang relevan (gf-style buckets).
// - Menggunakan payload ringan dan non-destruktif.
// - Mendeteksi pola error database untuk indikasi kuat SQLi (error-based).
//
// Catatan penting:
// - Ini tidak menjalankan time-based/blind SQLi (untuk menjaga kecepatan & etika).
// - Temuan dikembalikan sebagai "Possible SQL Injection (Error-based)" dengan confidence tinggi.
// - User diharapkan memvalidasi secara manual sebelum report ke program bug bounty.
type SQLiErrorContextModule struct {
	client        *http.Client
	payloads      []string
	errorPatterns []string
	maxTargets    int
	maxPerParam   int
}

// NewSQLiErrorContextModule creates a tuned instance suitable for -fullpower mode.
func NewSQLiErrorContextModule() *SQLiErrorContextModule {
	return &SQLiErrorContextModule{
		client: &http.Client{
			Timeout: 8 * time.Second,
		},
		// Minimal namun efektif untuk meng-trig error SQL.
		payloads: []string{
			"'",
			"\"",
			"' OR 1=1--",
		},
		// Pola error umum dari berbagai DBMS.
		errorPatterns: []string{
			"you have an error in your sql syntax",
			"warning: mysql",
			"mysql_fetch_array()",
			"pg_query():",
			"postgresql query failed",
			"unclosed quotation mark after the character string",
			"odbc sql server driver",
			"sqlstate[hy000]",
			"sqlstate[42000]",
			"syntax error in query expression",
			"native client",
		},
		// Batas protektif agar tidak terlalu agresif di -fullpower.
		maxTargets:  200, // batas jumlah endpoint-param yang diuji
		maxPerParam: 5,   // batas kombinasi payload per param
	}
}

func (m *SQLiErrorContextModule) Name() string {
	return "SQLiError"
}

func (m *SQLiErrorContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	if ctx == nil {
		return nil, nil
	}

	concurrency := ctx.GetConcurrency()
	if concurrency < 1 {
		concurrency = 5
	}

	type job struct {
		Endpoint core.EndpointParam
	}

	var targets []job

	// 1. Prioritas: gunakan ctx.Buckets.SQLi (hasil klasifikasi gf-style)
	for _, ep := range ctx.Buckets.SQLi {
		targets = append(targets, job{Endpoint: ep})
	}

	// 2. Fallback: jika bucket kosong, coba infer dari LiveURLs
	if len(targets) == 0 {
		for _, raw := range ctx.LiveURLs {
			u, err := url.Parse(raw)
			if err != nil {
				continue
			}
			q := u.Query()
			for name := range q {
				if isLikelySQLiParam(name) {
					targets = append(targets, job{
						Endpoint: core.EndpointParam{
							URL:   raw,
							Param: name,
						},
					})
				}
			}
		}
	}

	if len(targets) == 0 {
		return nil, nil
	}

	// Batasi jumlah target agar tidak berlebihan
	if len(targets) > m.maxTargets {
		targets = targets[:m.maxTargets]
	}

	findingsChan := make(chan core.Finding, len(targets)*2)
	errChan := make(chan error, 1)
	sem := make(chan struct{}, concurrency)

	for _, t := range targets {
		target := t

		sem <- struct{}{}
		go func() {
			defer func() { <-sem }()

			fs, err := m.testEndpointParam(ctx, target.Endpoint)
			if err != nil {
				// laporkan hanya error pertama untuk referensi
				select {
				case errChan <- err:
				default:
				}
				return
			}
			for _, f := range fs {
				findingsChan <- f
			}
		}()
	}

	// Tunggu semua goroutine selesai
	for i := 0; i < cap(sem); i++ {
		sem <- struct{}{}
	}
	close(findingsChan)
	close(errChan)

	var findings []core.Finding
	for f := range findingsChan {
		findings = append(findings, f)
	}

	// Abaikan error kecil; modul lain tetap jalan.
	return findings, nil
}

// testEndpointParam mencoba beberapa payload terhadap satu (URL,param)
// dan mengembalikan temuan jika menemukan pola error DB.
func (m *SQLiErrorContextModule) testEndpointParam(ctx *core.ScanContext, ep core.EndpointParam) ([]core.Finding, error) {
	var findings []core.Finding
	baseURL := ep.URL
	paramName := ep.Param

	if baseURL == "" || paramName == "" {
		return nil, nil
	}

	attempts := 0
	for _, p := range m.payloads {
		if attempts >= m.maxPerParam {
			break
		}
		attempts++

		testURL, ok := injectSQLiPayload(baseURL, paramName, p)
		if !ok {
			continue
		}

		body, status, err := m.httpGetBody(testURL)
		if err != nil || body == "" {
			continue
		}

		pattern := m.matchSQLError(body)
		if pattern == "" {
			// Beberapa implementasi juga memperhatikan perubahan pola respon,
			// tapi untuk menjaga akurasi & simple, kita fokus ke error jelas.
			continue
		}

		conf := 0.80
		if strings.Contains(strings.ToLower(p), "or 1=1") {
			conf = 0.86
		}

		targetBase := deriveTargetForURL(ctx, baseURL)

		findings = append(findings, core.Finding{
			Target:     targetBase,
			Endpoint:   testURL,
			Module:     m.Name(),
			Type:       "Possible SQL Injection (Error-based)",
			Severity:   "High",
			Confidence: conf,
			Evidence:   fmt.Sprintf("DB error pattern '%s' via param '%s' (HTTP %d)", pattern, paramName, status),
			Tags: []string{
				"sqli",
				"error-based",
				"param:" + paramName,
			},
		})

		// Satu bukti kuat cukup; hindari spam.
		break
	}

	return findings, nil
}

// injectSQLiPayload menyetel / mengganti nilai parameter dengan payload.
func injectSQLiPayload(rawURL, param, payload string) (string, bool) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return "", false
	}

	q := u.Query()
	q.Set(param, payload)
	u.RawQuery = q.Encode()

	return u.String(), true
}

// httpGetBody melakukan GET dan mengembalikan body dan status code.
func (m *SQLiErrorContextModule) httpGetBody(u string) (string, int, error) {
	resp, err := m.client.Get(u)
	if err != nil {
		return "", 0, err
	}
	if resp.Body == nil {
		return "", resp.StatusCode, nil
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", resp.StatusCode, err
	}
	return string(data), resp.StatusCode, nil
}

// matchSQLError mencari pola error SQL yang dikenal.
func (m *SQLiErrorContextModule) matchSQLError(body string) string {
	if body == "" {
		return ""
	}
	lower := strings.ToLower(body)
	for _, pat := range m.errorPatterns {
		if strings.Contains(lower, pat) {
			return pat
		}
	}
	return ""
}

// isLikelySQLiParam menilai apakah nama parameter "mencurigakan" untuk SQLi.
func isLikelySQLiParam(name string) bool {
	n := strings.ToLower(name)
	keywords := []string{
		"id", "uid", "user", "userid", "account",
		"post", "postid", "pid",
		"product", "item", "order",
		"cat", "category",
	}
	for _, kw := range keywords {
		if strings.Contains(n, kw) {
			return true
		}
	}
	return false
}

// deriveTargetForURL memetakan URL spesifik ke logical target di ScanContext.
// Helper ini didefinisikan di modul lain (misalnya XSS atau LFI) dan tidak perlu
// diduplikasi di sini untuk menghindari redeclare error.
