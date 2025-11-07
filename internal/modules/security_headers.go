package modules

import (
	"net/http"
	"time"

	"autohunt/internal/core"
)

// Legacy SecurityHeadersModule: kept for compatibility if needed elsewhere.
type SecurityHeadersModule struct{}

func NewSecurityHeadersModule() *SecurityHeadersModule {
	return &SecurityHeadersModule{}
}

func (m *SecurityHeadersModule) Name() string {
	return "SecurityHeaders"
}

func (m *SecurityHeadersModule) Run(targets []core.Target) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	required := []string{
		"Content-Security-Policy",
		"X-Frame-Options",
		"X-Content-Type-Options",
		"Strict-Transport-Security",
		"Referrer-Policy",
	}

	for _, t := range targets {
		resp, err := client.Get(t.URL)
		if err != nil {
			continue
		}
		resp.Body.Close()

		headers := resp.Header

		for _, h := range required {
			if headers.Get(h) == "" {
				severity := "Low"
				if h == "Content-Security-Policy" {
					severity = "Medium"
				}
				findings = append(findings, core.Finding{
					Target:     t.URL,
					Endpoint:   t.URL,
					Module:     m.Name(),
					Type:       "Missing Security Header: " + h,
					Severity:   severity,
					Confidence: 0.95,
					Evidence:   "Header not present",
					Tags:       []string{"hardening"},
				})
			}
		}
	}

	return findings, nil
}

// SecurityHeadersContextModule: ScanContext-based implementation.
type SecurityHeadersContextModule struct{}

func NewSecurityHeadersContextModule() *SecurityHeadersContextModule {
	return &SecurityHeadersContextModule{}
}

func (m *SecurityHeadersContextModule) Name() string {
	return "SecurityHeaders"
}

func (m *SecurityHeadersContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	required := []string{
		"Content-Security-Policy",
		"X-Frame-Options",
		"X-Content-Type-Options",
		"Strict-Transport-Security",
		"Referrer-Policy",
	}

	for _, t := range ctx.Targets {
		resp, err := client.Get(t.URL)
		if err != nil {
			continue
		}
		resp.Body.Close()

		headers := resp.Header

		for _, h := range required {
			if headers.Get(h) == "" {
				severity := "Low"
				if h == "Content-Security-Policy" {
					severity = "Medium"
				}
				findings = append(findings, core.Finding{
					Target:     t.URL,
					Endpoint:   t.URL,
					Module:     m.Name(),
					Type:       "Missing Security Header: " + h,
					Severity:   severity,
					Confidence: 0.95,
					Evidence:   "Header not present",
					Tags:       []string{"hardening"},
				})
			}
		}
	}

	return findings, nil
}
