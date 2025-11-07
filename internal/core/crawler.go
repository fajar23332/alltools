package core

import (
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"
)

type CrawledEndpoint struct {
	URL    string
	Params []string
}

var hrefRegex = regexp.MustCompile(`href=["']([^"'#?]+(?:\?[^"']*)?)["']`)
var sameHostOnly = true

// CrawlBasic is the original single-threaded crawler (kept for compatibility).
// For better performance, prefer CrawlBasicWithConcurrency.
func CrawlBasic(start Target, max int) []CrawledEndpoint {
	return CrawlBasicWithConcurrency(start, max, 10)
}

// CrawlBasicWithConcurrency performs a bounded-BFS crawl starting from start.URL,
// using a worker pool limited by the given concurrency value.
//
// Behavior:
// - Hanya mengikuti link dengan host yang sama (sameHostOnly).
// - Mengumpulkan hingga max endpoint unik (URL + param names).
// - Menggunakan timeout HTTP yang ketat agar tidak menggantung.
// - Aman digunakan sebagai bagian dari full recon pipeline.
func CrawlBasicWithConcurrency(start Target, max int, concurrency int) []CrawledEndpoint {
	if concurrency < 1 {
		concurrency = 1
	}

	client := &http.Client{Timeout: 8 * time.Second}

	visited := make(map[string]bool)
	var results []CrawledEndpoint

	queue := []string{start.URL}
	var mu sync.Mutex
	var wg sync.WaitGroup
	sem := make(chan struct{}, concurrency)

	for len(queue) > 0 && len(results) < max {
		current := queue[0]
		queue = queue[1:]

		mu.Lock()
		if visited[current] || len(results) >= max {
			mu.Unlock()
			continue
		}
		visited[current] = true
		mu.Unlock()

		wg.Add(1)
		sem <- struct{}{}
		go func(u string) {
			defer wg.Done()
			defer func() { <-sem }()

			resp, err := client.Get(u)
			if err != nil || resp.Body == nil {
				if resp != nil && resp.Body != nil {
					resp.Body.Close()
				}
				return
			}
			bodyBytes, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			body := string(bodyBytes)

			// Extract query params for this URL
			if cu, err := url.Parse(u); err == nil {
				q := cu.Query()
				var params []string
				for name := range q {
					params = append(params, name)
				}

				if len(params) > 0 {
					mu.Lock()
					if len(results) < max {
						results = append(results, CrawledEndpoint{
							URL:    u,
							Params: params,
						})
					}
					mu.Unlock()
				}
			}

			// Find links in page body
			matches := hrefRegex.FindAllStringSubmatch(body, -1)
			if len(matches) == 0 {
				return
			}

			var newURLs []string
			for _, m := range matches {
				href := strings.TrimSpace(m[1])
				if href == "" {
					continue
				}

				nu, err := url.Parse(href)
				if err != nil {
					continue
				}

				// Make absolute relative to start
				if !nu.IsAbs() {
					base, _ := url.Parse(start.URL)
					nu = base.ResolveReference(nu)
				}

				// Same-host only (safety)
				if sameHostOnly {
					su, _ := url.Parse(start.URL)
					if su.Host != nu.Host {
						continue
					}
				}

				if nu.Scheme != "http" && nu.Scheme != "https" {
					continue
				}

				normalized := nu.String()

				mu.Lock()
				if !visited[normalized] && len(results) < max {
					visited[normalized] = true
					newURLs = append(newURLs, normalized)
				}
				mu.Unlock()
			}

			if len(newURLs) > 0 {
				mu.Lock()
				queue = append(queue, newURLs...)
				mu.Unlock()
			}
		}(current)
	}

	wg.Wait()
	return results
}
