package modules

import (
	"fmt"
	"strings"

	"autohunt/internal/core"
)

// CVEFingerprintContextModule:
// Modul ini melakukan fingerprint teknologi dari hasil recon dan memberi indikasi
// potensi kerentanan (CVE / misconfig) berdasarkan pola umum yang dikenal.
//
// CATATAN PENTING:
// - Modul ini TIDAK mengklaim eksploit valid, hanya memberikan "strong hints".
// - Tujuan utama: membantu hunter memprioritaskan target & path eksploitasi.
// - Tanggung jawab user: memvalidasi manual berdasarkan evidence & referensi resmi.
//
// Sumber data:
// - ctx.Recon: hasil ReconBasic/FullRecon (Server, X-Powered-By, tech hints)
// - ctx.LiveURLs: bisa dipakai untuk heuristic tambahan jika diinginkan.
type CVEFingerprintContextModule struct{}

// NewCVEFingerprintContextModule mengembalikan instance modul context-based.
func NewCVEFingerprintContextModule() *CVEFingerprintContextModule {
	return &CVEFingerprintContextModule{}
}

func (m *CVEFingerprintContextModule) Name() string {
	return "CVEFingerprint"
}

func (m *CVEFingerprintContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	if ctx == nil || len(ctx.Recon) == 0 {
		return nil, nil
	}

	var findings []core.Finding

	for _, r := range ctx.Recon {
		target := r.Target
		serverLower := strings.ToLower(r.Server)
		poweredLower := strings.ToLower(r.PoweredBy)

		// Gabungkan semua hints teknologi dalam satu slice untuk dianalisa.
		var hints []string
		for _, t := range r.Technologies {
			hints = append(hints, strings.ToLower(t))
		}
		if r.Server != "" {
			hints = append(hints, "server:"+serverLower)
		}
		if r.PoweredBy != "" {
			hints = append(hints, "powered-by:"+poweredLower)
		}

		// WordPress
		if containsAnyLower(hints,
			[]string{"app:wordpress", "wordpress", "wp-content"}) {
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "Potential WordPress-related Vulnerabilities",
				Severity:   "Medium",
				Confidence: 0.6,
				Evidence:   "Detected patterns indicating WordPress. Check plugins, themes, and core version for known CVEs.",
				Tags:       []string{"cve", "wordpress", "fingerprint"},
			})
		}

		// phpMyAdmin
		if strings.Contains(serverLower, "php") || strings.Contains(poweredLower, "php") {
			// Ini indikasi umum stack PHP, bukan langsung CVE phpMyAdmin.
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "PHP Stack Detected",
				Severity:   "Info",
				Confidence: 0.5,
				Evidence:   "Server/X-Powered-By indicates PHP. Review for known PHP app misconfig/CVEs.",
				Tags:       []string{"php", "fingerprint"},
			})
		}

		// Apache / Nginx / IIS versi spesifik (heuristik sederhana)
		if strings.Contains(serverLower, "apache") {
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "Apache HTTPD Detected",
				Severity:   "Info",
				Confidence: 0.5,
				Evidence:   fmt.Sprintf("Server header: %s (check version-specific CVEs)", r.Server),
				Tags:       []string{"apache", "cve-hint", "fingerprint"},
			})
		}
		if strings.Contains(serverLower, "nginx") {
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "nginx Detected",
				Severity:   "Info",
				Confidence: 0.5,
				Evidence:   fmt.Sprintf("Server header: %s (check config & version CVEs)", r.Server),
				Tags:       []string{"nginx", "cve-hint", "fingerprint"},
			})
		}
		if strings.Contains(serverLower, "microsoft-iis") {
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "Microsoft IIS Detected",
				Severity:   "Info",
				Confidence: 0.6,
				Evidence:   fmt.Sprintf("Server header: %s (check IIS CVEs & misconfig)", r.Server),
				Tags:       []string{"iis", "cve-hint", "fingerprint"},
			})
		}

		// Laravel / Framework lain dari X-Powered-By atau hints
		if strings.Contains(poweredLower, "laravel") || containsAnyLower(hints, []string{"laravel"}) {
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "Laravel Framework Detected",
				Severity:   "Info",
				Confidence: 0.7,
				Evidence:   "Detected Laravel-related header / tech hints. Review for env exposure, debug mode, CVEs.",
				Tags:       []string{"laravel", "cve-hint", "fingerprint"},
			})
		}

		// Cloudflare / WAF hints - bukan CVE tapi penting untuk strategi
		if containsAnyLower(hints, []string{"waf:cloudflare"}) || strings.Contains(serverLower, "cloudflare") {
			findings = append(findings, core.Finding{
				Target:     target,
				Endpoint:   target,
				Module:     m.Name(),
				Type:       "Cloudflare/WAF Detected",
				Severity:   "Info",
				Confidence: 0.9,
				Evidence:   "Traffic seems behind Cloudflare/WAF. Some direct-origin bugs may be hidden.",
				Tags:       []string{"waf", "cloudflare", "fingerprint"},
			})
		}
	}

	// De-duplicate basic (by Target+Endpoint+Type+Module) agar output lebih bersih.
	dedup := make(map[string]core.Finding)
	for _, f := range findings {
		key := f.Target + "|" + f.Endpoint + "|" + f.Module + "|" + f.Type
		if _, ok := dedup[key]; !ok {
			dedup[key] = f
		}
	}
	out := make([]core.Finding, 0, len(dedup))
	for _, f := range dedup {
		out = append(out, f)
	}

	return out, nil
}

// containsAnyLower mengecek apakah s mengandung salah satu substring dari list (case-insensitive).
func containsAnyLower(slice []string, needles []string) bool {
	for _, item := range slice {
		l := strings.ToLower(item)
		for _, n := range needles {
			if n != "" && strings.Contains(l, strings.ToLower(n)) {
				return true
			}
		}
	}
	return false
}
