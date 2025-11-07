package core

import (
	"net/http"
	"strings"
	"sync"
	"time"
)

// ReconResult holds lightweight reconnaissance data for a single target.
type ReconResult struct {
	Target       string   `json:"target"`
	Status       string   `json:"status"`       // e.g. "up", "down", "timeout"
	HTTPCode     int      `json:"http_code"`    // last seen HTTP status code
	Server       string   `json:"server"`       // from Server header if present
	PoweredBy    string   `json:"powered_by"`   // from X-Powered-By header if present
	Technologies []string `json:"technologies"` // naive tech hints from headers/body
}

// ReconBasic performs a fast, low-impact HTTP reconnaissance for each target (sequential).
// Kept for backward compatibility. Prefer ReconBasicWithConcurrency in new code.
func ReconBasic(targets []Target) []ReconResult {
	return ReconBasicWithConcurrency(targets, 10)
}

// ReconBasicWithConcurrency performs HTTP reconnaissance with a bounded worker pool.
func ReconBasicWithConcurrency(targets []Target, concurrency int) []ReconResult {
	if concurrency < 1 {
		concurrency = 1
	}
	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	results := make([]ReconResult, len(targets))
	var wg sync.WaitGroup
	sem := make(chan struct{}, concurrency)

	for i, t := range targets {
		wg.Add(1)
		go func(idx int, target Target) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			res := ReconResult{
				Target:       target.URL,
				Status:       "down",
				HTTPCode:     0,
				Server:       "",
				PoweredBy:    "",
				Technologies: []string{},
			}

			req, err := http.NewRequest("GET", target.URL, nil)
			if err != nil {
				results[idx] = res
				return
			}
			req.Header.Set("User-Agent", "autohunt-recon/1.0")

			resp, err := client.Do(req)
			if err != nil {
				results[idx] = res
				return
			}

			res.HTTPCode = resp.StatusCode
			if resp.StatusCode > 0 {
				res.Status = "up"
			}

			server := strings.TrimSpace(resp.Header.Get("Server"))
			if server != "" {
				res.Server = server
				res.Technologies = append(res.Technologies, "server:"+server)
			}

			powered := strings.TrimSpace(resp.Header.Get("X-Powered-By"))
			if powered != "" {
				res.PoweredBy = powered
				res.Technologies = append(res.Technologies, "powered-by:"+powered)
			}

			const maxBodyRead = 4096
			buf := make([]byte, maxBodyRead)
			n, _ := resp.Body.Read(buf)
			resp.Body.Close()

			if n > 0 {
				body := strings.ToLower(string(buf[:n]))
				hints := detectTechFromBody(body)
				if len(hints) > 0 {
					res.Technologies = append(res.Technologies, hints...)
				}
			}

			results[idx] = res
		}(i, t)
	}

	wg.Wait()
	return results
}

// detectTechFromBody performs simple, cheap pattern matching on a (partial) HTML body
// to guess common technologies. It is intentionally conservative; it only adds hints.
func detectTechFromBody(body string) []string {
	var tech []string

	if strings.Contains(body, "wp-content/") || strings.Contains(body, "wordpress") {
		tech = append(tech, "app:wordpress")
	}
	if strings.Contains(body, "drupal.settings") {
		tech = append(tech, "app:drupal")
	}
	if strings.Contains(body, "content=\"joomla!") {
		tech = append(tech, "app:joomla")
	}
	if strings.Contains(body, "powered by prestashop") {
		tech = append(tech, "app:prestashop")
	}
	if strings.Contains(body, "var magentoInit") {
		tech = append(tech, "app:magento")
	}
	if strings.Contains(body, "cloudflare") {
		tech = append(tech, "waf:cloudflare")
	}
	if strings.Contains(body, "akamai") {
		tech = append(tech, "cdn:akamai")
	}

	return tech
}
