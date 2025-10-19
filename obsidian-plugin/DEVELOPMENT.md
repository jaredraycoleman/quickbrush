# QuickBrush Obsidian Plugin - Development Guide

## Prerequisites

- Node.js 16+
- npm or yarn
- Obsidian installed (for testing)

## Setup

1. Clone the repository
2. Navigate to the plugin directory:
   ```bash
   cd obsidian-plugin
   ```

3. Install dependencies:
   ```bash
   npm install
   ```

## Development Workflow

### Build for Development

Run the development build with hot reload:

```bash
npm run dev
```

This will:
- Watch for file changes
- Automatically rebuild on save
- Generate source maps for debugging

### Build for Production

Create an optimized production build:

```bash
npm run build
```

This will:
- Build without source maps
- Optimize and tree-shake the code
- Generate `main.js` ready for distribution

## Testing in Obsidian

### Option 1: Symlink (Recommended)

1. Build the plugin:
   ```bash
   npm run dev
   ```

2. Create a symlink to your test vault:
   ```bash
   # Linux/Mac
   ln -s /path/to/quickbrush/obsidian-plugin /path/to/your/vault/.obsidian/plugins/quickbrush

   # Windows (Run as Administrator)
   mklink /D "C:\path\to\vault\.obsidian\plugins\quickbrush" "C:\path\to\quickbrush\obsidian-plugin"
   ```

3. Enable the plugin in Obsidian:
   - Open Settings → Community Plugins
   - Reload plugins
   - Enable QuickBrush

4. Make changes to the code
5. Reload the plugin in Obsidian (Ctrl/Cmd+R or use Command Palette)

### Option 2: Manual Copy

1. Build the plugin:
   ```bash
   npm run build
   ```

2. Copy files to your vault's plugins folder:
   ```bash
   cp main.js manifest.json styles.css /path/to/vault/.obsidian/plugins/quickbrush/
   ```

3. Reload Obsidian or the plugin

## Project Structure

```
obsidian-plugin/
├── main.ts                 # Main plugin code
├── manifest.json           # Plugin manifest
├── package.json            # Node dependencies
├── tsconfig.json           # TypeScript configuration
├── esbuild.config.mjs      # Build configuration
├── version-bump.mjs        # Version management script
├── versions.json           # Version history
├── styles.css              # Plugin styles
├── .gitignore             # Git ignore rules
├── .npmrc                 # npm configuration
├── README.md              # User documentation
└── DEVELOPMENT.md         # This file
```

## Key Components

### QuickBrushPlugin Class

Main plugin class that:
- Loads settings
- Registers commands and ribbon icons
- Manages API communication
- Handles folder creation
- Creates gallery notes

### GenerateModal Class

Modal dialog for image generation:
- Displays generation options
- Validates user input
- Calls API and handles responses
- Shows progress notifications

### QuickBrushSettingTab Class

Settings panel for:
- API key configuration
- Folder path customization
- Account information display

## API Integration

The plugin communicates with the QuickBrush API using Obsidian's `requestUrl` function:

```typescript
const response = await requestUrl({
	url: `${this.settings.apiUrl}/generate`,
	method: 'POST',
	headers: {
		'Authorization': `Bearer ${this.settings.apiKey}`,
		'Content-Type': 'application/json'
	},
	body: JSON.stringify(options)
});
```

### Endpoints Used

- `POST /api/generate` - Generate image
- `GET /api/image/{generation_id}` - Download generated image
- `GET /api/user` - Get user account info

## TypeScript Configuration

The plugin uses TypeScript with strict null checks:

```json
{
	"compilerOptions": {
		"target": "ES6",
		"module": "ESNext",
		"strictNullChecks": true,
		"moduleResolution": "node"
	}
}
```

## Build System

Uses esbuild for fast compilation:

- **Development**: Includes source maps, watches for changes
- **Production**: Optimized bundle, no source maps, tree-shaking

## Versioning

To bump the version:

```bash
npm version patch  # 1.0.0 -> 1.0.1
npm version minor  # 1.0.0 -> 1.1.0
npm version major  # 1.0.0 -> 2.0.0
```

This automatically:
- Updates `package.json`
- Updates `manifest.json`
- Updates `versions.json`
- Creates a git tag

## Debugging

### Enable Developer Tools in Obsidian

1. Open Obsidian
2. Press `Ctrl+Shift+I` (Windows/Linux) or `Cmd+Option+I` (Mac)
3. Go to Console tab
4. Look for logs from the plugin

### Adding Debug Logs

```typescript
console.log('QuickBrush: Generating image with options:', options);
```

### Common Issues

**Plugin not loading:**
- Check Console for errors
- Verify `main.js` exists and is built
- Check `manifest.json` is valid JSON

**API calls failing:**
- Check Network tab in DevTools
- Verify API key is set
- Check API URL is correct

## Best Practices

1. **Always test in a test vault** - Don't develop in your main vault
2. **Use TypeScript types** - Leverage type safety
3. **Handle errors gracefully** - Show user-friendly error messages
4. **Follow Obsidian conventions** - Use Obsidian's APIs and patterns
5. **Keep dependencies minimal** - Avoid unnecessary npm packages

## Resources

- [Obsidian Plugin Developer Documentation](https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin)
- [Obsidian API Reference](https://github.com/obsidianmd/obsidian-api)
- [Sample Plugin](https://github.com/obsidianmd/obsidian-sample-plugin)
- [QuickBrush API Documentation](https://quickbrush.online/api/docs)

## Publishing

When ready to publish:

1. Ensure all tests pass
2. Update version number
3. Build production version: `npm run build`
4. Create a GitHub release with:
   - `main.js`
   - `manifest.json`
   - `styles.css`
5. Submit to Obsidian Community Plugins

## Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

MIT License - See LICENSE file for details
