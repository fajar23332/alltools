package modules

import (
	"io"
	"net/http"
	"strings"
	"time"

	"autohunt/internal/core"
)

type DirListingModule struct {
	paths []string
}

func NewDirListingModule() *DirListingModule {
	return &DirListingModule{
		paths: []string{
			"/",
			"/backup/",
			"/old/",
			"/uploads/",
			"/files/",
		},
	}
}

func (m *DirListingModule) Name() string {
	return "DirListing"
}

func (m *DirListingModule) Run(targets []core.Target) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	for _, t := range targets {
		for _, p := range m.paths {
			url := strings.TrimRight(t.URL, "/") + p
			resp, err := client.Get(url)
			if err != nil || resp.StatusCode != 200 {
				if resp != nil && resp.Body != nil {
					resp.Body.Close()
				}
				continue
			}
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()

			if strings.Contains(string(body), "Index of /") {
				findings = append(findings, core.Finding{
					Target:     t.URL,
					Endpoint:   url,
					Module:     m.Name(),
					Type:       "Directory Listing Enabled",
					Severity:   "Medium",
					Confidence: 0.9,
					Evidence:   "Page contains 'Index of /'",
					Tags:       []string{"info-leak"},
				})
			}
		}
	}

	return findings, nil
}

// DirListingContextModule implements directory listing checks using ScanContext.
// It reuses the same logic as DirListingModule, but reads targets from ctx.Targets.
type DirListingContextModule struct {
	paths []string
}

func NewDirListingContextModule() *DirListingContextModule {
	return &DirListingContextModule{
		paths: []string{
			"/",
			"/backup/",
			"/old/",
			"/uploads/",
			"/files/",
		},
	}
}

func (m *DirListingContextModule) Name() string {
	return "DirListing"
}

func (m *DirListingContextModule) Run(ctx *core.ScanContext) ([]core.Finding, error) {
	client := &http.Client{Timeout: 7 * time.Second}
	var findings []core.Finding

	for _, t := range ctx.Targets {
		for _, p := range m.paths {
			url := strings.TrimRight(t.URL, "/") + p
			resp, err := client.Get(url)
			if err != nil || resp.StatusCode != 200 {
				if resp != nil && resp.Body != nil {
					resp.Body.Close()
				}
				continue
			}
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()

			if strings.Contains(string(body), "Index of /") {
				findings = append(findings, core.Finding{
					Target:     t.URL,
					Endpoint:   url,
					Module:     m.Name(),
					Type:       "Directory Listing Enabled",
					Severity:   "Medium",
					Confidence: 0.9,
					Evidence:   "Page contains 'Index of /'",
					Tags:       []string{"info-leak"},
				})
			}
		}
	}

	return findings, nil
}
