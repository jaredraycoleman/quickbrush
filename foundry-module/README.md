# Quickbrush for Foundry VTT

AI-powered image generation for Foundry Virtual Tabletop. Bring Your Own Key (BYOK).

**A tool by Wizzlethorpe Labs.**

## Features

- **Generate images** for actors (characters, NPCs, creatures) and items
- **Bring Your Own Key**: Uses your OpenAI API key—you control costs and privacy
- **Reference images**: Upload up to 3 reference images for style/character consistency
- **Quality options**: Low, Medium, High
- **Aspect ratios**: Square, Landscape, Portrait
- **Seamless integration**: Right-click menu on actors/items to generate images

## Installation

In Foundry VTT, go to **Add-on Modules → Install Module** and paste:

```
https://github.com/wizzlethorpe/quickbrush/releases/latest/download/module.json
```

Or install manually from the [GitHub releases page](https://github.com/wizzlethorpe/quickbrush/releases).

## Setup

1. Get your OpenAI API key from [platform.openai.com](https://platform.openai.com)
2. Open **Module Settings → Quickbrush**
3. Enter your OpenAI API key
4. (Optional) Choose your preferred image model (gpt-image-1-mini recommended for speed)

## Usage

### Generate Actor Images

1. Right-click on any Actor (character/NPC/creature)
2. Select **Generate Image**
3. The description will auto-populate from the actor's bio/notes
4. Optionally add a context prompt or reference images
5. Click **Generate**
6. The generated image will be set as the actor's portrait automatically

### Generate Item Images

1. Right-click on any Item
2. Select **Generate Item Image**
3. Description auto-populates from item description
4. Adjust quality and aspect ratio as needed
5. Click **Generate**
6. Image is set as the item's icon automatically

## Settings

- **OpenAI API Key**: Your API key from platform.openai.com
- **Image Model**: gpt-image-1-mini (faster/cheaper) or gpt-image-1 (higher quality)
- **Save Folder**: Folder name in Foundry's data directory for generated images

## Pricing

Uses your OpenAI API key—you only pay for what you use:

- **gpt-image-1-mini**: ~$0.01-0.05 per image (recommended)
- **gpt-image-1**: ~$0.03-0.15 per image (higher quality)

Check [OpenAI's pricing page](https://openai.com/pricing) for current rates.

## Support

- GitHub: [wizzlethorpe/quickbrush](https://github.com/wizzlethorpe/quickbrush)
- Report issues: [GitHub Issues](https://github.com/wizzlethorpe/quickbrush/issues)
- Website: [quickbrush.wizzlethorpe.com](https://quickbrush.wizzlethorpe.com)

## License

MIT
