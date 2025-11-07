#!/bin/bash
# Sync the core library to all consuming projects

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CORE_SOURCE="$PROJECT_ROOT/packages/quickbrush-core/src/index.js"

echo "Syncing quickbrush-core to all projects..."

# Sync to Foundry module
echo "  → foundry-module/scripts/quickbrush-core.js"
cp "$CORE_SOURCE" "$PROJECT_ROOT/foundry-module/scripts/quickbrush-core.js"

# Sync to docs (website)
echo "  → docs/js/quickbrush-core.js"
cp "$CORE_SOURCE" "$PROJECT_ROOT/docs/js/quickbrush-core.js"

# Note: Obsidian plugin currently uses the API service, not the core library
# When it switches to BYOK, add:
# cp "$CORE_SOURCE" "$PROJECT_ROOT/quickbrush-obsidian-plugin/src/quickbrush-core.js"

echo "✓ Core library synced successfully!"
