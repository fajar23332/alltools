package core

import (
    "context"
    "sync"
    "time"
)

type Engine struct {
    modules []Module
    timeout time.Duration
}

func NewEngine(timeout time.Duration, modules []Module) *Engine {
    return &Engine{
        modules: modules,
        timeout: timeout,
    }
}

func (e *Engine) Run(targets []Target) ([]Finding, error) {
    ctx, cancel := context.WithTimeout(context.Background(), e.timeout)
    defer cancel()

    findingsChan := make(chan []Finding, len(e.modules))
    errChan := make(chan error, len(e.modules))

    var wg sync.WaitGroup
    for _, m := range e.modules {
        mod := m
        wg.Add(1)
        go func() {
            defer wg.Done()
            select {
            case <-ctx.Done():
                return
            default:
                res, err := mod.Run(targets)
                if err != nil {
                    errChan <- err
                    return
                }
                if len(res) > 0 {
                    findingsChan <- res
                }
            }
        }()
    }

    wg.Wait()
    close(findingsChan)
    close(errChan)

    var all []Finding
    for fs := range findingsChan {
        all = append(all, fs...)
    }

    // Untuk V1, error modul tidak menghentikan semua proses.
    return all, nil
}
