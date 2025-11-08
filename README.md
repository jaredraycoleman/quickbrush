# Quickbrush

AI-powered fantasy RPG artwork for Foundry VTT, Obsidian, and the web. Built by Wizzlethorpe Labs.

## Project Structure

This is a monorepo containing the Quickbrush core library and multiple platform implementations:

```
quickbrush/
├── packages/
│   └── quickbrush-core/          # Shared image generation logic
├── foundry-module/               # Foundry VTT module
├── quickbrush-obsidian-plugin/   # Obsidian plugin
├── docs/                         # Static website
└── scripts/                      # Build and sync scripts
```

## Quick Start

### Installation

Install all dependencies:

```bash
npm install
```

### Building

Build all projects:

```bash
npm run build:all
```

Or build individually:

```bash
npm run build:foundry    # Sync core to Foundry module
npm run build:docs       # Sync core to docs (website)
npm run build:obsidian   # Build Obsidian plugin
```

### Syncing Core Library

After making changes to `packages/quickbrush-core/src/index.js`:

```bash
npm run sync-core
```

This will copy the core library to all consuming projects.

## Project Details

### Core Library (`packages/quickbrush-core`)

The shared business logic for image generation. Contains:
- OpenAI API client
- Generator classes (Character, Scene, Creature, Item)
- Common image generation logic

**Key principle:** Single source of truth for generation logic.

See [packages/quickbrush-core/README.md](packages/quickbrush-core/README.md) for details.

### Foundry VTT Module (`foundry-module/`)

FoundryVTT module that allows users to generate artwork using their own OpenAI API key (BYOK).

- Uses bundled core library (`foundry-module/scripts/quickbrush-core.js`)
- Integrates with Foundry's Actor and Item sheets
- Supports reference images and custom prompts

### Obsidian Plugin (`quickbrush-obsidian-plugin/`)

Obsidian plugin for generating and managing RPG artwork in your vault.

- Uses core library with BYOK (Bring Your Own Key)
- Requires user's OpenAI API key
- TypeScript with esbuild bundling
- Core library is bundled into the plugin build

### Website (`docs/`)

Static website for quickbrush.ai with demo/generation interface.

- Uses bundled core library (`docs/js/quickbrush-core.js`)
- Pure HTML/CSS/JavaScript (no build step)

## Development Workflow

### Making Changes to Core Library

1. Edit `packages/quickbrush-core/src/index.js`
2. Run `npm run sync-core` to distribute changes
3. Test in each platform:
   - **Website:** Open `docs/generate.html` in browser
   - **Foundry:** Test in Foundry VTT instance
   - **Obsidian:** Build and test plugin

### Adding New Features

When adding features to the core library:

1. Add the feature to `packages/quickbrush-core/src/index.js`
2. Update exports if needed
3. Run `npm run sync-core`
4. Update platform-specific code as needed
5. Document in the core README

### Git Workflow

The core library is the source of truth. Other copies are build artifacts:

```bash
# Only commit changes to the core library source
git add packages/quickbrush-core/src/index.js

# The synced files are also committed for deployment
git add foundry-module/scripts/quickbrush-core.js
git add docs/js/quickbrush-core.js
```

### Creating Releases

Use the automated release script:

```bash
npm run release
```

The script will:
1. Prompt you to select platform (Foundry/Obsidian/Both)
2. Ask for version increment (patch/minor/major/custom)
3. Request release notes
4. Build and package everything
5. Create GitHub releases with proper tags
6. Upload all necessary assets

See [scripts/README.md](scripts/README.md) for detailed documentation.

## Scripts

| Script | Description |
|--------|-------------|
| `npm install` | Install all dependencies (workspace-aware) |
| `npm run sync-core` | Copy core library to all consuming projects |
| `npm run build:all` | Build all projects |
| `npm run build:foundry` | Sync core to Foundry module |
| `npm run build:docs` | Sync core to docs (website) |
| `npm run build:obsidian` | Build Obsidian plugin |
| `npm run release` | Automated release script for packaging and releasing |

## Architecture

### Why This Structure?

This monorepo uses a **shared library with platform-specific consumers** approach:

**Benefits:**
- ✅ Single source of truth for business logic
- ✅ Easy to maintain and update core functionality
- ✅ Each platform can use the library in the most appropriate way
- ✅ No complex build pipeline needed for static sites
- ✅ Version controlled together for consistency

**Trade-offs:**
- The core library is copied to consuming projects (not dynamically linked)
- Must run `npm run sync-core` after core changes
- Synced files should be committed for deployment

### Alternative Approaches Considered

1. **Git Submodules:** More complex, harder to maintain
2. **Published NPM Package:** Overkill for private monorepo
3. **Dynamic URL Loading:** Unreliable, requires network access
4. **Separate Repos:** Difficult to keep in sync

## License

MIT

## Support

For issues or questions, visit [quickbrush.wizzlethorpe.com](https://quickbrush.wizzlethorpe.com)
