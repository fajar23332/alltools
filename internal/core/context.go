package core

type EndpointParam struct {
	URL   string `json:"url"`
	Param string `json:"param"`
}

type ClassifiedBuckets struct {
	SQLi         []EndpointParam `json:"sqli"`
	XSS          []EndpointParam `json:"xss"`
	LFI          []EndpointParam `json:"lfi"`
	OpenRedirect []EndpointParam `json:"open_redirect"`
	SSRF         []EndpointParam `json:"ssrf"`
}

// ScanContext menyimpan seluruh hasil recon dan context yang digunakan oleh modul-modul.
// Field Concurrency digunakan untuk mengontrol tingkat paralelisme HTTP scan di modul,
// misalnya diimplementasikan sebagai jumlah worker goroutine.
type ScanContext struct {
	Targets      []Target          `json:"targets"`
	Recon        []ReconResult     `json:"recon"`
	URLPool      []string          `json:"url_pool"`
	LiveURLs     []string          `json:"live_urls"`
	Buckets      ClassifiedBuckets `json:"buckets"`
	ExternalUsed []string          `json:"external_used"`
	Concurrency  int               `json:"concurrency"`
	// Aggressive mode:
	// - Diaktifkan ketika user menjalankan --fullpower-aggressive / -fa
	// - Mengizinkan modul untuk:
	//   - Menambah variasi payload aman
	//   - Memperluas jumlah endpoint/kombinasi yang diuji
	//   - Tetap dengan batasan yang mencegah DoS/kerusakan
	Aggressive bool `json:"aggressive"`
}

// GetConcurrency mengembalikan nilai concurrency yang aman untuk digunakan modul.
// Jika nilai tidak di-set (0 atau negatif), akan mengembalikan default (misal 10).
func (ctx *ScanContext) GetConcurrency() int {
	if ctx == nil {
		return 10
	}
	if ctx.Concurrency <= 0 {
		return 10
	}
	return ctx.Concurrency
}

// IsAggressive mengembalikan true jika ScanContext berada dalam mode agresif (-fa).
// Modul dapat menggunakan nilai ini untuk:
// - Menambah cakupan payload & kombinasi secara aman,
// - Tanpa melampaui batas etis (tidak DoS, tidak destructive).
func (ctx *ScanContext) IsAggressive() bool {
	if ctx == nil {
		return false
	}
	return ctx.Aggressive
}
