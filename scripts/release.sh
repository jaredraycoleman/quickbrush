#!/bin/bash
# Release script for Quickbrush Foundry Module and Obsidian Plugin
# Creates GitHub releases with proper assets for both platforms

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to increment version
increment_version() {
    local version=$1
    local type=$2

    IFS='.' read -ra ADDR <<< "$version"
    major="${ADDR[0]}"
    minor="${ADDR[1]}"
    patch="${ADDR[2]}"

    case $type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            print_error "Invalid version type: $type"
            exit 1
            ;;
    esac

    echo "$major.$minor.$patch"
}

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    print_error "GitHub CLI (gh) is not installed. Install it from https://cli.github.com/"
    exit 1
fi

# Check if logged in to GitHub
if ! gh auth status &> /dev/null; then
    print_error "Not logged in to GitHub. Run 'gh auth login' first."
    exit 1
fi

# Get current versions
cd "$PROJECT_ROOT"

FOUNDRY_VERSION=$(jq -r '.version' foundry-module/module.json)
OBSIDIAN_VERSION=$(jq -r '.version' quickbrush-obsidian-plugin/manifest.json)

print_info "Current Foundry version: $FOUNDRY_VERSION"
print_info "Current Obsidian version: $OBSIDIAN_VERSION"

# Ask which platform to release
echo ""
echo "Which platform do you want to release?"
echo "1) Foundry Module"
echo "2) Obsidian Plugin"
echo "3) Both"
read -p "Enter choice (1-3): " platform_choice

# Ask for version increment type
echo ""
echo "How do you want to increment the version?"
echo "1) Patch (x.x.X) - Bug fixes"
echo "2) Minor (x.X.0) - New features"
echo "3) Major (X.0.0) - Breaking changes"
echo "4) Custom version"
read -p "Enter choice (1-4): " version_choice

# Determine new versions
if [ "$version_choice" == "4" ]; then
    read -p "Enter custom version (e.g., 2.1.0): " NEW_VERSION
    NEW_FOUNDRY_VERSION="$NEW_VERSION"
    NEW_OBSIDIAN_VERSION="$NEW_VERSION"
else
    case $version_choice in
        1) increment_type="patch" ;;
        2) increment_type="minor" ;;
        3) increment_type="major" ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac

    NEW_FOUNDRY_VERSION=$(increment_version "$FOUNDRY_VERSION" "$increment_type")
    NEW_OBSIDIAN_VERSION=$(increment_version "$OBSIDIAN_VERSION" "$increment_type")
fi

print_info "New Foundry version will be: $NEW_FOUNDRY_VERSION"
print_info "New Obsidian version will be: $NEW_OBSIDIAN_VERSION"

# Ask for release notes
echo ""
read -p "Enter release notes (or press Enter to use editor): " release_notes

if [ -z "$release_notes" ]; then
    # Create temp file for release notes
    TEMP_NOTES=$(mktemp)
    echo "# Release Notes for v$NEW_FOUNDRY_VERSION" > "$TEMP_NOTES"
    echo "" >> "$TEMP_NOTES"
    echo "## Changes" >> "$TEMP_NOTES"
    echo "- " >> "$TEMP_NOTES"

    ${EDITOR:-nano} "$TEMP_NOTES"
    release_notes=$(cat "$TEMP_NOTES")
    rm "$TEMP_NOTES"
fi

# Confirm release
echo ""
print_warn "About to create release with the following details:"
echo "  Platform: $platform_choice"
[ "$platform_choice" != "2" ] && echo "  Foundry: v$NEW_FOUNDRY_VERSION"
[ "$platform_choice" != "1" ] && echo "  Obsidian: v$NEW_OBSIDIAN_VERSION"
echo ""
read -p "Continue? (y/N): " confirm

if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    print_info "Release cancelled"
    exit 0
fi

# Update Foundry Module
if [ "$platform_choice" == "1" ] || [ "$platform_choice" == "3" ]; then
    print_info "Updating Foundry module version..."

    # Update module.json
    jq ".version = \"$NEW_FOUNDRY_VERSION\" | .download = \"https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/download/foundry-v$NEW_FOUNDRY_VERSION/quickbrush-foundry-v$NEW_FOUNDRY_VERSION.zip\"" \
        foundry-module/module.json > foundry-module/module.json.tmp
    mv foundry-module/module.json.tmp foundry-module/module.json

    # Sync core library
    npm run sync-core

    # Create release directory
    FOUNDRY_RELEASE_DIR="$PROJECT_ROOT/releases/foundry-v$NEW_FOUNDRY_VERSION"
    mkdir -p "$FOUNDRY_RELEASE_DIR"

    # Copy files to release directory
    print_info "Preparing Foundry release files..."
    cp -r foundry-module/* "$FOUNDRY_RELEASE_DIR/"

    # Create zip file
    cd "$PROJECT_ROOT/releases"
    zip -r "quickbrush-foundry-v$NEW_FOUNDRY_VERSION.zip" "foundry-v$NEW_FOUNDRY_VERSION"

    print_info "Created Foundry release zip: quickbrush-foundry-v$NEW_FOUNDRY_VERSION.zip"

    cd "$PROJECT_ROOT"
fi

# Update Obsidian Plugin
if [ "$platform_choice" == "2" ] || [ "$platform_choice" == "3" ]; then
    print_info "Updating Obsidian plugin version..."

    # Update manifest.json and versions.json
    jq ".version = \"$NEW_OBSIDIAN_VERSION\"" quickbrush-obsidian-plugin/manifest.json > quickbrush-obsidian-plugin/manifest.json.tmp
    mv quickbrush-obsidian-plugin/manifest.json.tmp quickbrush-obsidian-plugin/manifest.json

    # Update versions.json
    VERSIONS_JSON=$(jq ". + {\"$NEW_OBSIDIAN_VERSION\": \"0.15.0\"}" quickbrush-obsidian-plugin/versions.json)
    echo "$VERSIONS_JSON" > quickbrush-obsidian-plugin/versions.json

    # Build plugin
    print_info "Building Obsidian plugin..."
    npm run build:obsidian

    # Create release directory
    OBSIDIAN_RELEASE_DIR="$PROJECT_ROOT/releases/obsidian-v$NEW_OBSIDIAN_VERSION"
    mkdir -p "$OBSIDIAN_RELEASE_DIR"

    # Copy release files
    print_info "Preparing Obsidian release files..."
    cp quickbrush-obsidian-plugin/main.js "$OBSIDIAN_RELEASE_DIR/"
    cp quickbrush-obsidian-plugin/manifest.json "$OBSIDIAN_RELEASE_DIR/"
    cp quickbrush-obsidian-plugin/styles.css "$OBSIDIAN_RELEASE_DIR/"

    # Create zip file
    cd "$PROJECT_ROOT/releases"
    zip -r "quickbrush-obsidian-v$NEW_OBSIDIAN_VERSION.zip" "obsidian-v$NEW_OBSIDIAN_VERSION"

    print_info "Created Obsidian release files"

    cd "$PROJECT_ROOT"
fi

# Commit version changes
print_info "Committing version changes..."

# Handle Foundry module (regular files)
if [ "$platform_choice" == "1" ] || [ "$platform_choice" == "3" ]; then
    git add foundry-module/module.json
    # Also add synced core library if it was updated
    git add foundry-module/scripts/quickbrush-core.js
fi

# Handle Obsidian plugin (submodule)
if [ "$platform_choice" == "2" ] || [ "$platform_choice" == "3" ]; then
    print_info "Committing Obsidian submodule changes..."
    cd quickbrush-obsidian-plugin
    git add manifest.json versions.json
    git commit -m "chore: Bump version to v$NEW_OBSIDIAN_VERSION"
    git push
    cd "$PROJECT_ROOT"

    # Update submodule reference in main repo
    git add quickbrush-obsidian-plugin
fi

# Commit in main repo
if [ "$platform_choice" == "1" ]; then
    git commit -m "chore: Release Foundry module v$NEW_FOUNDRY_VERSION"
elif [ "$platform_choice" == "2" ]; then
    git commit -m "chore: Update Obsidian plugin to v$NEW_OBSIDIAN_VERSION"
else
    git commit -m "chore: Release v$NEW_FOUNDRY_VERSION / Obsidian v$NEW_OBSIDIAN_VERSION"
fi

# Push changes
print_info "Pushing changes to GitHub..."
git push

# Create GitHub releases
if [ "$platform_choice" == "1" ] || [ "$platform_choice" == "3" ]; then
    print_info "Creating Foundry GitHub release..."

    gh release create "foundry-v$NEW_FOUNDRY_VERSION" \
        --title "Foundry Module v$NEW_FOUNDRY_VERSION" \
        --notes "$release_notes" \
        "releases/quickbrush-foundry-v$NEW_FOUNDRY_VERSION.zip" \
        "foundry-module/module.json#module.json"

    # Also create/update 'latest-foundry' tag
    git tag -f "latest-foundry" "foundry-v$NEW_FOUNDRY_VERSION"
    git push -f origin "latest-foundry"

    print_info "✓ Foundry release created: foundry-v$NEW_FOUNDRY_VERSION"
fi

if [ "$platform_choice" == "2" ] || [ "$platform_choice" == "3" ]; then
    print_info "Creating Obsidian GitHub release..."

    gh release create "obsidian-v$NEW_OBSIDIAN_VERSION" \
        --title "Obsidian Plugin v$NEW_OBSIDIAN_VERSION" \
        --notes "$release_notes" \
        "releases/quickbrush-obsidian-v$NEW_OBSIDIAN_VERSION.zip" \
        "releases/obsidian-v$NEW_OBSIDIAN_VERSION/main.js#main.js" \
        "releases/obsidian-v$NEW_OBSIDIAN_VERSION/manifest.json#manifest.json" \
        "releases/obsidian-v$NEW_OBSIDIAN_VERSION/styles.css#styles.css"

    # Also create/update 'latest-obsidian' tag
    git tag -f "latest-obsidian" "obsidian-v$NEW_OBSIDIAN_VERSION"
    git push -f origin "latest-obsidian"

    print_info "✓ Obsidian release created: obsidian-v$NEW_OBSIDIAN_VERSION"
fi

# Cleanup
print_info "Cleaning up release files..."
rm -rf "$PROJECT_ROOT/releases"

print_info ""
print_info "🎉 Release completed successfully!"
print_info ""

if [ "$platform_choice" == "1" ] || [ "$platform_choice" == "3" ]; then
    print_info "Foundry Module:"
    print_info "  Version: v$NEW_FOUNDRY_VERSION"
    print_info "  Release: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/foundry-v$NEW_FOUNDRY_VERSION"
fi

if [ "$platform_choice" == "2" ] || [ "$platform_choice" == "3" ]; then
    print_info "Obsidian Plugin:"
    print_info "  Version: v$NEW_OBSIDIAN_VERSION"
    print_info "  Release: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/obsidian-v$NEW_OBSIDIAN_VERSION"
fi
