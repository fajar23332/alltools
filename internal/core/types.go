package core

// Target represents a single normalized target URL (scheme + host + base path).
type Target struct {
	URL string `json:"url"`
}

// Finding represents a single vulnerability or interesting security observation
// produced by any scanning engine (nuclei, ffuf, dsb) yang diorkestrasi autohunt.
type Finding struct {
	Target     string   `json:"target"`         // Logical target (e.g. base URL / domain)
	Endpoint   string   `json:"endpoint"`       // Specific URL tested
	Module     string   `json:"module"`         // Module/tool name that produced this finding (e.g. "nuclei", "ffuf")
	Type       string   `json:"type"`           // Short classification / template ID / description
	Severity   string   `json:"severity"`       // Info/Low/Medium/High/Critical
	Confidence float64  `json:"confidence"`     // 0.0 - 1.0 confidence score
	Evidence   string   `json:"evidence"`       // Key evidence snippet or explanation
	Tags       []string `json:"tags,omitempty"` // Extra labels (e.g. ["nuclei","cve-2023-xxxx","xss"])
}

// Module and ContextModule are kept temporarily for backward compatibility with
// legacy internal scanners. In the new design, autohunt primarily orchestrates
// external tools (subfinder, httpx, gau, nuclei, ffuf) and maps their results
// into Finding structs.

// Module is the legacy interface implemented by pre-context modules.
type Module interface {
	Name() string
	Run(targets []Target) ([]Finding, error)
}

// ContextModule is the legacy interface for ScanContext-based internal modules.
type ContextModule interface {
	// Name returns a stable identifier for the module (used in logs & findings).
	Name() string

	// Run executes the module's logic using the aggregated ScanContext.
	Run(ctx *ScanContext) ([]Finding, error)
}

// External orchestration helpers untuk tools seperti subfinder/httpx/gau/nuclei/ffuf
// didefinisikan dan diimplementasikan pada file core lain (misal fullrecon.go atau
// file orkestrator khusus). File ini hanya menyimpan tipe dasar (Target, Finding,
// Module, ContextModule) dan ScanContext (di context.go).
