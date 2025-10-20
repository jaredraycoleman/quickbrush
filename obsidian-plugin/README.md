# QuickBrush for Obsidian

Generate AI-powered images directly from your Obsidian notes using QuickBrush. Create character portraits, scenes, creatures, and items with just a few clicks.

## Features

- **Four Generation Types**: Character, Scene, Creature, and Item images
- **Smart Text Extraction**: Automatically extracts content from your active note
- **Quality Options**: Choose from Low (1 brushstroke), Medium (3 brushstrokes), or High (5 brushstrokes)
- **Multiple Aspect Ratios**: Square, Landscape, or Portrait
- **Organized Storage**: All files organized in a single parent folder:
  - Images saved to `Quickbrush/quickbrush-images`
  - Gallery notes in `Quickbrush/quickbrush-gallery`
  - Gallery index at `Quickbrush/quickbrush-generations.base` (Dataview query)
- **Gallery Notes**: Each generation creates a timestamped note with:
  - Embedded image
  - Generation metadata (type, quality, aspect ratio, etc.)
  - Original and refined descriptions
  - Automatic chronological ordering
- **Dataview Integration**: Auto-generated `.base` file for viewing all generations in a table

## Installation

### From Source

1. Clone or download this plugin to your vault's `.obsidian/plugins/quickbrush/` folder
2. Run `npm install` in the plugin directory
3. Run `npm run build` to compile the plugin
4. Enable the plugin in Obsidian's Community Plugins settings

### Manual Installation

1. Create a folder named `quickbrush` in your vault's `.obsidian/plugins/` directory
2. Copy `main.js`, `manifest.json`, and `styles.css` into the folder
3. Enable the plugin in Obsidian's Community Plugins settings

## Setup

1. Get your API key from [quickbrush.online](https://quickbrush.online)
2. Open Settings → QuickBrush
3. Enter your API key
4. (Optional) Customize the parent folder name (default: "Quickbrush")
   - Images will be saved to: `{folder}/quickbrush-images`
   - Gallery notes will be saved to: `{folder}/quickbrush-gallery`
   - Gallery index will be created at: `{folder}/quickbrush-generations.base`

## Usage

### Generate from Active Note

1. Open any note in Obsidian
2. Use one of these methods:
   - Click the QuickBrush ribbon icon
   - Open Command Palette (Ctrl/Cmd+P) and search for "QuickBrush"
   - Use a specific command:
     - "QuickBrush: Generate Character Image"
     - "QuickBrush: Generate Scene Image"
     - "QuickBrush: Generate Creature Image"
     - "QuickBrush: Generate Item Image"

3. The plugin will automatically extract text from your note (excluding frontmatter)
4. The first 3 images embedded in your note will be automatically selected as reference images
5. You can add or remove reference images using the "Add Image" button
6. Adjust the description, type, quality, and aspect ratio as needed
7. Click "Generate"

### Reference Images

The plugin supports up to 3 reference images to guide the generation:

- **Auto-Selected**: The first 3 images from your active note are automatically extracted
- **Manual Selection**: Click "Add Image" to select additional images from your device
- **Remove Images**: Click the × button on any thumbnail to remove it
- **Supported Formats**: PNG, JPG, JPEG, GIF, WebP, BMP

Reference images help maintain consistency with existing artwork or provide visual style guidance.

### Generation Options

**Generation Types:**
- **Character**: For character portraits and NPCs (default: square)
- **Scene**: For locations, environments, and scenes (default: landscape)
- **Creature**: For monsters, beasts, and creatures (default: square)
- **Item**: For equipment, artifacts, and items (default: square)

**Quality Levels:**
- **Low**: 1 brushstroke, faster generation
- **Medium**: 3 brushstrokes, balanced quality
- **High**: 5 brushstrokes, best quality

**Aspect Ratios:**
- **Square**: 1024x1024 (general purpose)
- **Landscape**: 1536x1024 (wide scenes)
- **Portrait**: 1024x1536 (tall compositions)

## Gallery Notes

Each generated image creates a gallery note with this structure:

```markdown
---
date: "2025-01-15T10:30:00.000Z"
generation_type: "character"
quality: "medium"
aspect_ratio: "square"
brushstrokes_used: 3
original_description: "Your original description..."
refined_description: "AI-enhanced description..."
prompt: "Optional context prompt"
---

![[quickbrush-images/quickbrush-abc123.webp]]
```

Gallery notes are automatically named with timestamps (e.g., `2025-01-15 103045.md`) for chronological ordering.

## Settings

- **API Key**: Your QuickBrush API key
- **API URL**: QuickBrush API endpoint (default: https://quickbrush.online/api)
- **QuickBrush Folder**: Parent folder for all QuickBrush files (default: `Quickbrush`)
  - Images: `{folder}/quickbrush-images`
  - Gallery: `{folder}/quickbrush-gallery`
  - Index: `{folder}/quickbrush-generations.base`

## Gallery Index

The plugin automatically creates a `quickbrush-generations.base` file in your QuickBrush folder. This file contains a Dataview query that displays all your generations in a sortable table:

```dataview
TABLE WITHOUT ID
	file.link as "Generation",
	date as "Date",
	generation_type as "Type",
	quality as "Quality",
	aspect_ratio as "Aspect Ratio",
	brushstrokes_used as "Brushstrokes"
FROM "Quickbrush/quickbrush-gallery"
SORT date DESC
```

To view this table, you need to have the [Dataview plugin](https://github.com/blacksmithgu/obsidian-dataview) installed. The file is automatically updated when you change the QuickBrush folder setting.

## Example Workflow

1. Create a character note:
```markdown
---
name: Elara Moonwhisper
race: Elf
class: Wizard
---

# Elara Moonwhisper

A wise elf wizard with silver hair and piercing blue eyes.
She wears flowing robes adorned with celestial symbols and
carries an ancient staff topped with a glowing crystal.
```

2. Run "QuickBrush: Generate Character Image"
3. The plugin extracts the description automatically
4. Optionally add a context prompt like "the character is smiling and has a painted face"
5. Click Generate
6. Image appears in `quickbrush-images/` and a gallery note is created in `quickbrush-gallery/`

## Troubleshooting

**"Please set your QuickBrush API key in settings"**
- You need to configure your API key in Settings → QuickBrush

**"Invalid API key"**
- Check that your API key is correct
- Get a new key from [quickbrush.online](https://quickbrush.online)

**"Insufficient brushstrokes"**
- Visit [quickbrush.online](https://quickbrush.online) to purchase more brushstrokes

**"Rate limit exceeded"**
- Wait a few seconds before generating another image
- Current limits: 1 per 10 seconds, 50 per hour

## Support

- Website: [quickbrush.online](https://quickbrush.online)
- Report issues: [GitHub Issues](https://github.com/yourusername/quickbrush/issues)

## License

MIT License - See LICENSE file for details
