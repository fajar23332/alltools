package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"time"

	"autohunt/internal/core"
	"autohunt/internal/modules"
)

// This main implements a full-power pipeline using ScanContext:
//
// 1) Target initialization
// 2) FullRecon:
//    - Basic HTTP recon
//    - URL pool (crawler + static paths + optional external tools / historical sources)
//    - Live URL filter (httpx-style / internal)
//    - Param classification into buckets (gf-style)
// 3) Vulnerability scanning:
//    - Modules operate on ScanContext (buckets + targets + recon)
// 4) Optional FFUF fuzzing (--fuzzing)
// 5) Reporting

func main() {
	// CLI flags
	target := flag.String("u", "", "Single target URL or domain, e.g. https://example.com or example.com")
	targetsFile := flag.String("f", "", "File with list of targets (one per line)")
	output := flag.String("o", "autohunt_result.json", "Output JSON file")
	timeout := flag.Int("timeout", 900, "Max scan time in seconds (global)")
	concurrency := flag.Int("c", 10, "Maximum concurrent HTTP operations (tuning: 5-50)")
	verbose := flag.Bool("v", false, "Verbose output")
	fuzzing := flag.Bool("fuzzing", false, "Run ffuf-based fuzzing after vulnerability scanning (requires ffuf in PATH and FUZZ URL)")

	// Full-power modes:
	// --fullpower / -F  : mode maksimal yang menjalankan seluruh pipeline recon + modul vuln secara terstruktur.
	// --fullpower-aggressive / -fa :
	//   mode sangat agresif (disarankan hanya di VPS / environment kuat),
	//   meningkatkan intensitas dan cakupan scan sehingga lebih mendekati coverage maksimum.
	fullpower := flag.Bool("fullpower", true, "Enable full-power mode: orchestrated recon + external tools + targeted vuln scanning")
	flag.BoolVar(fullpower, "F", true, "Alias for --fullpower")

	fullpowerAggressive := flag.Bool("fullpower-aggressive", false, "EXTREME mode: very aggressive full-power scanning, recommended ONLY on VPS (high load, wide coverage)")
	flag.BoolVar(fullpowerAggressive, "fa", false, "Alias for --fullpower-aggressive")

	flag.Parse()

	// Stage 1: Target initialization
	stageBanner("STAGE 1: TARGET INITIALIZATION")

	if *target == "" && *targetsFile == "" {
		log.Fatalf("[!] Please provide either -u <url/domain> or -f <file>")
	}

	// Jika mode agresif diaktifkan, paksa fullpower aktif juga.
	if *fullpowerAggressive {
		*fullpower = true
	}

	targets, err := core.LoadTargets(*target, *targetsFile)
	if err != nil {
		log.Fatalf("[!] Failed to load targets: %v", err)
	}
	if len(targets) == 0 {
		log.Fatalf("[!] No valid targets loaded")
	}
	fmt.Printf("[*] Loaded %d target(s)\n", len(targets))

	// Stage 2: Recon / FullRecon
	var scanCtx *core.ScanContext
	globalDeadline := time.Now().Add(time.Duration(*timeout) * time.Second)
	if *concurrency < 1 {
		*concurrency = 1
	}

	if *fullpower && !*fullpowerAggressive {
		stageBanner("STAGE 2: FULL RECON (internal + optional external)")
		start := time.Now()
		scanCtx = core.FullReconWithConcurrency(targets, true, *verbose, *concurrency)
		fmt.Printf("[*] FullRecon completed in %s\n", time.Since(start).Truncate(time.Millisecond))
		fmt.Printf("[*] URL pool: %d, live URLs: %d\n", len(scanCtx.URLPool), len(scanCtx.LiveURLs))
		if len(scanCtx.ExternalUsed) > 0 {
			fmt.Printf("[*] External recon tools leveraged: %v\n", scanCtx.ExternalUsed)
		}
	} else if *fullpowerAggressive {
		stageBanner("STAGE 2: FULL RECON AGGRESSIVE (-fullpower-aggressive / -fa)")
		fmt.Println("[!] WARNING: Aggressive mode is resource-intensive. Strongly recommended to run on a VPS or powerful machine.")
		fmt.Println("[!] This mode increases breadth/depth of scanning and may generate significant traffic (still non-destructive).")

		// Jika user tidak set -c, gunakan nilai concurrency default yang lebih tinggi untuk -fa
		if flag.Lookup("c").Value.String() == "10" {
			// Naikkan default concurrency khusus untuk mode agresif
			*concurrency = 40
			fmt.Printf("[*] Aggressive mode: concurrency auto-set to %d (override with -c if needed)\n", *concurrency)
		}

		start := time.Now()
		scanCtx = core.FullReconWithConcurrency(targets, true, *verbose, *concurrency)
		// Tandai context sebagai agresif agar modul bisa memperluas cakupan payload & kombinasi secara aman.
		if scanCtx != nil {
			scanCtx.Aggressive = true
		}
		fmt.Printf("[*] Aggressive FullRecon completed in %s\n", time.Since(start).Truncate(time.Millisecond))
		fmt.Printf("[*] URL pool: %d, live URLs: %d\n", len(scanCtx.URLPool), len(scanCtx.LiveURLs))
		if len(scanCtx.ExternalUsed) > 0 {
			fmt.Printf("[*] External recon tools leveraged (aggressive): %v\n", scanCtx.ExternalUsed)
		}
	} else {
		stageBanner("STAGE 2: BASIC RECON")
		start := time.Now()
		recon := core.ReconBasicWithConcurrency(targets, *concurrency)

		scanCtx = &core.ScanContext{
			Targets: targets,
			Recon:   recon,
		}
		fmt.Printf("[*] Basic recon completed in %s\n", time.Since(start).Truncate(time.Millisecond))

		// Minimal URL pool for non-fullpower mode: crawl each target lightly
		for _, t := range targets {
			eps := core.CrawlBasicWithConcurrency(t, 40, *concurrency)
			for _, ep := range eps {
				scanCtx.URLPool = append(scanCtx.URLPool, ep.URL)
			}
		}
		scanCtx.LiveURLs = scanCtx.URLPool
		scanCtx.Buckets = core.ClassifyParams(scanCtx.LiveURLs)

		if *verbose {
			for _, r := range recon {
				fmt.Printf("    - %s [%s] tech=%v\n", r.Target, r.Status, r.Technologies)
			}
		}
	}

	if scanCtx == nil || len(scanCtx.Targets) == 0 {
		log.Fatalf("[!] Scan context initialization failed")
	}

	if *verbose {
		fmt.Printf("[*] Bucket summary: SQLi=%d, XSS=%d, LFI=%d, Redirect=%d, SSRF=%d\n",
			len(scanCtx.Buckets.SQLi),
			len(scanCtx.Buckets.XSS),
			len(scanCtx.Buckets.LFI),
			len(scanCtx.Buckets.OpenRedirect),
			len(scanCtx.Buckets.SSRF),
		)
	}

	// Stage 3: Vulnerability scanning with ScanContext-aware modules
	stageBanner("STAGE 3: VULNERABILITY SCANNING")

	// Define modules using the new ContextModule interface.
	// Each module reads from scanCtx (targets, buckets, live URLs, etc).
	modGroups := []struct {
		Title   string
		Modules []core.ContextModule
	}{
		{
			Title: "Surface & Misconfiguration Checks",
			Modules: []core.ContextModule{
				modules.NewSensitiveFilesContextModule(),
				modules.NewDirListingContextModule(),
				modules.NewSecurityHeadersContextModule(),
				modules.NewCORSContextModule(),
			},
		},
		{
			Title: "Injection, File Inclusion & Redirect/SSRF Checks",
			Modules: []core.ContextModule{
				modules.NewXSSReflectContextModule(),
				modules.NewSQLiErrorContextModule(),
				modules.NewLFIBasicContextModule(),
				modules.NewOpenRedirectContextModule(),
				modules.NewSSRFContextModule(),
			},
		},
		{
			Title: "Technology & Fingerprint Intelligence",
			Modules: []core.ContextModule{
				modules.NewCVEFingerprintContextModule(),
			},
		},
	}

	var allFindings []core.Finding

	for gi, group := range modGroups {
		if time.Now().After(globalDeadline) {
			fmt.Printf("[!] Global timeout reached before group %d (%s)\n", gi+1, group.Title)
			break
		}

		fmt.Printf("\n--- [%d/%d] %s ---\n", gi+1, len(modGroups), group.Title)

		for mi, mod := range group.Modules {
			if time.Now().After(globalDeadline) {
				fmt.Printf("[!] Global timeout reached before module %s\n", mod.Name())
				break
			}

			fmt.Printf("[*] [%d.%d] Running module: %s ... ", gi+1, mi+1, mod.Name())
			start := time.Now()
			findings, err := runContextModuleWithBudget(mod, scanCtx, globalDeadline, *concurrency)
			duration := time.Since(start).Truncate(time.Millisecond)

			if err != nil {
				fmt.Printf("ERR (%s): %v\n", duration, err)
				continue
			}

			fmt.Printf("OK (%s), findings: %d\n", duration, len(findings))
			if *verbose && len(findings) > 0 {
				for _, f := range findings {
					fmt.Printf("    - [%s] %s | %s | %s\n", f.Severity, f.Module, f.Endpoint, f.Type)
				}
			}

			allFindings = append(allFindings, findings...)
		}
	}

	// Optional: FFUF-based fuzzing (separate from main recon/vuln pipeline)
	// Hanya dijalankan jika user menambahkan --fuzzing.
	// Perilaku:
	// - Menggunakan ffuf (jika tersedia di PATH)
	// - Target URL otomatis dipastikan mengandung FUZZ (append /FUZZ jika belum ada)
	// - Menggunakan wordlists/dirs_common.txt sebagai wordlist utama
	// - Menambah temuan ke allFindings sebagai Module="FFUF" dengan tag "sensitive(ffuf)"
	if *fuzzing {
		stageBanner("STAGE 4: FFUF FUZZING (--fuzzing)")
		ffufFindings, err := modules.RunFFUFFuzzing(scanCtx, *concurrency, *verbose)
		if err != nil {
			fmt.Printf("[!] FFUF fuzzing error: %v\n", err)
		} else {
			fmt.Printf("[*] FFUF findings: %d\n", len(ffufFindings))
			allFindings = append(allFindings, ffufFindings...)
		}
	}

	// Stage 5: Reporting
	stageBanner("STAGE 5: REPORT")
	fmt.Printf("[*] Total findings: %d\n", len(allFindings))

	if err := core.SaveFindingsJSON(*output, allFindings); err != nil {
		fmt.Printf("[!] Failed to save JSON report: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("[+] Scan complete. Results saved to %s\n", *output)
}

// stageBanner prints a clean stage separator.
func stageBanner(title string) {
	fmt.Println()
	fmt.Println("==================================================")
	fmt.Println(title)
	fmt.Println("==================================================")
}

// runContextModuleWithBudget runs a ContextModule with respect to the global deadline.
func runContextModuleWithBudget(mod core.ContextModule, ctx *core.ScanContext, globalDeadline time.Time, concurrency int) ([]core.Finding, error) {
	remaining := time.Until(globalDeadline)
	if remaining <= 0 {
		return nil, fmt.Errorf("global timeout exceeded before module %s", mod.Name())
	}
	return mod.Run(ctx)
}
