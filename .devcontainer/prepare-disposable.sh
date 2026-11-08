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
if [[ ! -f config/configuration.yaml ]]; then
    git archive HEAD config | tar -x
fi
# tmpfs also resets on stop. Dev Container clients run postStartCommand on restart.
if [[ ${1:-} == --restore ]]; then
    if [[ ! -x node_modules/.bin/prettier ]]; then
        npm ci --silent
    fi
    if [[ ! -d config/custom_components/hacs ]]; then
        script/setup/install-hacs
    fi
fi
