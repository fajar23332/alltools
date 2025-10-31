#!/usr/bin/env bash

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
setup-rust() {
  log "Checking Rust..."
  if ! command -v cargo >/dev/null 2>&1; then
    log "Installing Rust..."
    curl https://sh.rustup.rs -sSf | sh -s -- -y
    source "$HOME/.cargo/env"
  fi
  log "Rust environment ready ✅"
}
