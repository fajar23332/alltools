package httpclient

import (
    "net"
    "net/http"
    "time"
)

func Default() *http.Client {
    tr := &http.Transport{
        MaxIdleConns:        100,
        IdleConnTimeout:     30 * time.Second,
        DisableCompression:  false,
        TLSHandshakeTimeout: 10 * time.Second,
        DialContext: (&net.Dialer{
            Timeout:   10 * time.Second,
            KeepAlive: 30 * time.Second,
        }).DialContext,
    }
    return &http.Client{
        Timeout:   15 * time.Second,
        Transport: tr,
    }
}
