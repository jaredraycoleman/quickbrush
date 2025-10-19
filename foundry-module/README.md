# Quickbrush AI Image Generator for Foundry VTT

Generate stunning AI-powered fantasy RPG artwork directly in Foundry VTT using [Quickbrush](https://quickbrush.online). Create characters, scenes, creatures, and items from your journal notes with just a few clicks!

![Quickbrush](https://quickbrush.online/static/images/wispy.webp)

## Features

✨ **Generate Images Directly in Foundry**
- Create characters, scenes, creatures, and items
- Choose from low, medium, and high quality
- Select square, landscape, or portrait aspect ratios

🎨 **Smart Journal Integration**
- Add Quickbrush button to any journal page
- One-click generation from journal text
- Auto-populates description from journal content

📚 **Automatic Gallery**
- All images saved to `quickbrush-images` folder
- Automatic "Quickbrush Gallery" journal with all generations
- Easy browsing and organization

⚡ **Powerful Options**
- Artistic prompts for styling
- Quality control (1, 3, or 5 brushstrokes)
- Multiple aspect ratios
- Rate limit tracking

## Installation

### Method 1: Manifest URL (Recommended)

1. In Foundry VTT, go to **Add-on Modules**
2. Click **Install Module**
3. Paste this manifest URL:
   ```
   https://quickbrush.online/foundry-module/module.json
   ```
4. Click **Install**

### Method 2: Manual Installation

1. Download the latest release from [GitHub](https://github.com/quickbrush/foundry-module/releases)
2. Extract to your Foundry `Data/modules/` directory
3. Restart Foundry VTT
4. Enable the module in your world

## Setup

### 1. Get Your API Key

1. Go to [Quickbrush Dashboard](https://quickbrush.online/dashboard)
2. Click on **"Manage API Keys"**
3. Create a new API key
4. Copy the key (you'll only see it once!)

### 2. Configure the Module

1. In Foundry, go to **Game Settings** → **Configure Settings**
2. Find **"Quickbrush AI Image Generator"** in the modules list
3. Click **"Module Settings"**
4. Paste your API key in the **"API Key"** field
5. (Optional) Customize the save folder name

![Settings Screenshot](docs/settings.png)

## Usage

### Method 1: Scene Controls

1. Click the **Notes** tool in the scene controls (left sidebar)
2. Look for the **palette icon** (Quickbrush button)
3. Click it to open the generation dialog
4. Fill in your description and options
5. Click **"Generate Image"**

![Scene Controls](docs/scene-controls.png)

### Method 2: Journal Button (Recommended!)

1. Open any journal page
2. Click the **"Quickbrush"** button in the header
3. Select what type to generate (Character, Scene, Creature, or Item)
4. The dialog opens with journal text pre-populated!
5. Adjust and generate

![Journal Button](docs/journal-button.png)

### Generation Options

| Option | Description | Default |
|--------|-------------|---------|
| **Type** | Character, Scene, Creature, or Item | Character |
| **Description** | What you want to generate (required) | - |
| **Artistic Prompt** | Additional styling (optional) | - |
| **Quality** | Low (1), Medium (3), High (5 brushstrokes) | Medium |
| **Aspect Ratio** | Square, Landscape, or Portrait | Smart default based on type |

**Smart Defaults:**
- Scenes default to **landscape**
- Everything else defaults to **square**

## Examples

### Character Example

```
Type: Character
Description: A brave halfling with silver armor and a magic brush
Artistic Prompt: In golden light, heroic pose
Quality: High
Aspect Ratio: Square
```

### Scene Example

```
Type: Scene
Description: Ancient library filled with magical tomes and floating candles
Artistic Prompt: Misty atmosphere, warm lighting
Quality: Medium
Aspect Ratio: Landscape
```

### Creature Example

```
Type: Creature
Description: A majestic dragon with emerald scales
Artistic Prompt: Flying over mountains, dramatic clouds
Quality: High
Aspect Ratio: Landscape
```

## Gallery Management

All generated images are automatically:

1. **Saved** to the `quickbrush-images` folder (or your custom folder)
2. **Added** to the "Quickbrush Gallery" journal
3. **Organized** with metadata (type, date, quality, description)

The gallery journal entry includes:
- Image preview
- Generation type and date
- Original description
- Quality and aspect ratio
- Direct link to image

## Rate Limiting

Quickbrush enforces rate limits to ensure fair usage:

- **Short-term**: 1 generation per 10 seconds
- **Hourly**: 50 generations per hour

If you hit a rate limit, the module will show a friendly error message telling you how long to wait.

Check your current usage:
```javascript
const api = new Quickbrush.API();
const status = await api.getRateLimitStatus();
console.log(status);
```

## Brushstroke Costs

Image generation costs brushstrokes based on quality:

| Quality | Cost |
|---------|------|
| Low | 1 brushstroke |
| Medium | 3 brushstrokes |
| High | 5 brushstrokes |

Purchase brushstrokes or subscribe at [Quickbrush Dashboard](https://quickbrush.online/dashboard).

## Troubleshooting

### "Please set your Quickbrush API key"

**Solution:** Go to Module Settings and add your API key from [quickbrush.online/dashboard](https://quickbrush.online/dashboard).

### "Rate limit exceeded"

**Solution:** Wait the specified time before generating another image. The rate limits are:
- 1 per 10 seconds
- 50 per hour

### "Insufficient brushstrokes"

**Solution:** You've run out of brushstrokes! Visit [Quickbrush Dashboard](https://quickbrush.online/dashboard) to:
- Purchase a brushstroke pack (never expires)
- Subscribe for monthly allowances (best value!)

### "Failed to generate image"

**Possible causes:**
1. Invalid API key
2. Network connectivity issues
3. Quickbrush API is down (check [status page](https://quickbrush.online))

**Debug:**
```javascript
// Test API connection
const api = new Quickbrush.API();
try {
  const status = await api.getRateLimitStatus();
  console.log('API working:', status);
} catch (err) {
  console.error('API error:', err);
}
```

### Images not appearing in gallery

1. Check if "Quickbrush Gallery" journal exists
2. Verify images saved to `quickbrush-images` folder
3. Check browser console for errors (F12)

### Button not appearing on journal

1. Make sure module is enabled for your world
2. Refresh the page (F5)
3. Check if you're on a V13+ Foundry version

## API Reference

The module exposes a global `Quickbrush` object for programmatic access:

### Generate Image Programmatically

```javascript
const dialog = new Quickbrush.Dialog({
  data: {
    text: 'A mighty warrior',
    generation_type: 'character',
    quality: 'high',
    aspect_ratio: 'square'
  }
});
dialog.render(true);
```

### Check Rate Limits

```javascript
const api = new Quickbrush.API();
const status = await api.getRateLimitStatus();
console.log(`You have ${status.usage.hourly_remaining} generations remaining this hour`);
```

### Add to Gallery Manually

```javascript
await Quickbrush.Gallery.addToGallery({
  imageUrl: 'path/to/image.webp',
  type: 'character',
  description: 'A brave knight',
  prompt: 'In golden armor',
  quality: 'high',
  aspectRatio: 'square',
  generationId: 'some-id',
  refinedDescription: 'AI-enhanced description'
});
```

## Settings

| Setting | Description | Default |
|---------|-------------|---------|
| **API Key** | Your Quickbrush API key (required) | - |
| **API URL** | Quickbrush API endpoint | `https://quickbrush.online/api` |
| **Image Save Folder** | Where images are saved | `quickbrush-images` |

## Privacy & Security

- Your API key is stored securely in Foundry's world settings
- Only the GM needs to configure the API key
- Images are stored locally in your Foundry data directory
- API requests are sent directly to Quickbrush (HTTPS encrypted)

## Support

- **Documentation**: [https://quickbrush.online/docs](https://quickbrush.online/docs)
- **Support Email**: [support@quickbrush.online](mailto:support@quickbrush.online)
- **Bug Reports**: [GitHub Issues](https://github.com/quickbrush/foundry-module/issues)
- **Discord**: [Join our server](https://discord.gg/quickbrush)

## Pricing

Quickbrush uses a brushstroke-based pricing model:

**Subscriptions** (best value - 50% savings):
- Basic: $5/mo - 250 brushstrokes/month
- Pro: $10/mo - 500 brushstrokes/month
- Premium: $20/mo - 1000 brushstrokes/month
- Ultimate: $50/mo - 2500 brushstrokes/month

**One-Time Packs** (never expire):
- Small: $10 - 250 brushstrokes
- Medium: $20 - 500 brushstrokes
- Large: $40 - 1000 brushstrokes
- Mega: $100 - 2500 brushstrokes

Learn more at [quickbrush.online/dashboard](https://quickbrush.online/dashboard)

## Changelog

### Version 1.0.1 (2025-10-18)
- Initial release
- Image generation dialog
- Journal integration
- Automatic gallery
- Rate limit handling
- Quality and aspect ratio options

## License

This module is provided under the MIT License. See LICENSE file for details.

Quickbrush API and service are provided by Quickbrush ([quickbrush.online](https://quickbrush.online)).

## Credits

**Module Author**: Quickbrush Team
**Wispy (The Artist)**: Your friendly neighborhood halfling painter
**Powered by**: OpenAI DALL-E and GPT-4

---

Made with ❤️ by [Quickbrush](https://quickbrush.online)

*"Your adventure needs a splash of color!" — Wispy*
