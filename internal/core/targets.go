package core

import (
    "bufio"
    "net/url"
    "os"
    "strings"
)

func LoadTargets(single string, file string) ([]Target, error) {
    var targets []Target

    if single != "" {
        if t, ok := normalizeURL(single); ok {
            targets = append(targets, Target{URL: t})
        }
    }

    if file != "" {
        f, err := os.Open(file)
        if err != nil {
            return nil, err
        }
        defer f.Close()
        s := bufio.NewScanner(f)
        for s.Scan() {
            line := strings.TrimSpace(s.Text())
            if line == "" {
                continue
            }
            if t, ok := normalizeURL(line); ok {
                targets = append(targets, Target{URL: t})
            }
        }
    }

    return targets, nil
}

func normalizeURL(raw string) (string, bool) {
    if !strings.HasPrefix(raw, "http://") && !strings.HasPrefix(raw, "https://") {
        raw = "https://" + raw
    }
    u, err := url.Parse(raw)
    if err != nil || u.Host == "" {
        return "", false
    }
    if u.Path == "" {
        u.Path = "/"
    }
    return u.String(), true
}
