package modules

import (
	"net/http"
	"strings"
	"time"

	"autohunt/internal/core"
)

type CORSModule struct{}

func NewCORSModule() *CORSModule {
	return &CORSModule{}
}

func (m *CORSModule) Name() string {
	return "CORS"
}

func (m *CORSModule) Run(targets []core.Target) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	for _, t := range targets {
		req, _ := http.NewRequest("GET", t.URL, nil)
		req.Header.Set("Origin", "https://evil.example.com")

		resp, err := client.Do(req)
		if err != nil {
			continue
		}
		resp.Body.Close()

		acao := resp.Header.Get("Access-Control-Allow-Origin")
		acac := resp.Header.Get("Access-Control-Allow-Credentials")

		if acao == "*" && strings.ToLower(acac) == "true" {
			findings = append(findings, core.Finding{
				Target:     t.URL,
				Endpoint:   t.URL,
				Module:     m.Name(),
				Type:       "CORS Misconfiguration (* with credentials)",
				Severity:   "High",
				Confidence: 0.95,
				Evidence:   "ACAOrigin:* with ACAC:true",
				Tags:       []string{"cors", "misconfig"},
			})
		} else if acao == "*" {
			findings = append(findings, core.Finding{
				Target:     t.URL,
				Endpoint:   t.URL,
				Module:     m.Name(),
				Type:       "CORS: Wildcard Allow-Origin",
				Severity:   "Medium",
				Confidence: 0.8,
				Evidence:   "Access-Control-Allow-Origin:*",
				Tags:       []string{"cors"},
			})
		}
	}

	return findings, nil
}

// CORSContextModule implements CORS checks using ScanContext.
type CORSContextModule struct{}

func NewCORSContextModule() *CORSContextModule {
	return &CORSContextModule{}
}

func (m *CORSContextModule) Name() string {
	return "CORS"
}

func (m *CORSContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	for _, t := range ctx.Targets {
		req, _ := http.NewRequest("GET", t.URL, nil)
		// Simulate cross-origin request
		req.Header.Set("Origin", "https://evil.example.com")

		resp, err := client.Do(req)
		if err != nil {
			continue
		}
		resp.Body.Close()

		acao := resp.Header.Get("Access-Control-Allow-Origin")
		acac := resp.Header.Get("Access-Control-Allow-Credentials")

		if acao == "*" && strings.ToLower(acac) == "true" {
			findings = append(findings, core.Finding{
				Target:     t.URL,
				Endpoint:   t.URL,
				Module:     m.Name(),
				Type:       "CORS Misconfiguration (* with credentials)",
				Severity:   "High",
				Confidence: 0.95,
				Evidence:   "ACAOrigin:* with ACAC:true",
				Tags:       []string{"cors", "misconfig"},
			})
		} else if acao == "*" {
			findings = append(findings, core.Finding{
				Target:     t.URL,
				Endpoint:   t.URL,
				Module:     m.Name(),
				Type:       "CORS: Wildcard Allow-Origin",
				Severity:   "Medium",
				Confidence: 0.8,
				Evidence:   "Access-Control-Allow-Origin:*",
				Tags:       []string{"cors"},
			})
		}
	}

	return findings, nil
}
