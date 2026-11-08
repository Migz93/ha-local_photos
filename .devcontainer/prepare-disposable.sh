#!/usr/bin/env bash
# Seed a fresh in-memory HA config without reading saved host instance state.
set -euo pipefail
cd "$(dirname "$0")/.."
for target in config node_modules; do
    if ! mountpoint -q "$target" || [[ "$(stat -f -c %T "$target")" != tmpfs ]]; then
        echo "Expected disposable tmpfs mount at $target; refusing to use host data." >&2
        exit 1
    fi
    sudo chown "$(id -u):$(id -g)" "$target"
done
# Use tracked defaults only. Changes here are temporary and never replace host config.
git archive HEAD config | tar -x
