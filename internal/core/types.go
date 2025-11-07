package core

// Target represents a single normalized target URL (scheme + host + base path).
type Target struct {
	URL string `json:"url"`
}

// Finding represents a single vulnerability or interesting security observation
// produced by any scanning module.
type Finding struct {
	Target     string   `json:"target"`         // Logical target (e.g. base URL / domain)
	Endpoint   string   `json:"endpoint"`       // Specific URL tested
	Module     string   `json:"module"`         // Module name that produced this finding
	Type       string   `json:"type"`           // Short classification (e.g. "SQLi", "XSS", "LFI", "Sensitive File")
	Severity   string   `json:"severity"`       // Info/Low/Medium/High/Critical
	Confidence float64  `json:"confidence"`     // 0.0 - 1.0 confidence score
	Evidence   string   `json:"evidence"`       // Key evidence snippet or explanation
	Tags       []string `json:"tags,omitempty"` // Extra labels (e.g. ["xss","reflected","param:q"])
}

// Module is the legacy interface implemented by pre-context modules.
// It is kept temporarily for backward compatibility and will be deprecated
// once all modules are migrated to the ScanContext-based interface.
type Module interface {
	Name() string
	Run(targets []Target) ([]Finding, error)
}

// ContextModule is the core interface for ScanContext-based modules.
//
// Each ContextModule receives a *ScanContext that contains:
// - Targets
// - Recon results
// - URL pool and live URLs
// - Classified parameter buckets (gf-style)
// - Information about any external helpers used
//
// This allows the full-power pipeline to perform recon once and let all
// modules reuse the same intelligence, instead of duplicating work.
type ContextModule interface {
	// Name returns a stable identifier for the module (used in logs & findings).
	Name() string

	// Run executes the module's logic using the aggregated ScanContext.
	// Implementations should:
	// - Use ctx data read-only or in an additive, non-breaking way.
	// - Handle internal errors gracefully and report them via the returned error.
	Run(ctx *ScanContext) ([]Finding, error)
}
