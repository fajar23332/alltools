package core

import (
	"encoding/json"
	"os"
)

func SaveFindingsJSON(path string, findings []Finding) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	return enc.Encode(findings)
}
