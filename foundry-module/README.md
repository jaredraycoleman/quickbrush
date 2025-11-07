# Quickbrush AI Image Generator for Foundry VTT (BYOK Edition)

Generate stunning AI-powered fantasy RPG artwork directly in Foundry VTT using your own OpenAI API key. Create characters, scenes, creatures, and items from your journal notes with just a few clicks!

![Quickbrush](https://quickbrush.ai/static/images/wispy.webp)

## Features

✨ **Generate Images Directly in Foundry**
- Create characters, scenes, creatures, and items
- Choose from low, medium, and high quality (Standard or HD)
- Select square, landscape, or portrait aspect ratios (up to 1536x1024)

🎨 **Smart Journal Integration**
- Add Quickbrush button to any journal page
- One-click generation from journal text
- Auto-populates description from journal content
- Extract reference images from journal pages

📚 **Automatic Gallery**
- All images saved to `quickbrush-images` folder
- Automatic "Quickbrush Gallery" journal with all generations
- Easy browsing and organization

⚡ **Powerful Options**
- AI-powered description refinement with GPT-4o
- Context prompts for fine-grained results
- Reference images (up to 3) to guide generation
- Auto-update character/item images
- Quality control (Standard or HD)

🎭 **Deep Foundry Integration**
- Works with Character Sheets - extracts race, class, biography
- Works with NPC Sheets - extracts type, CR, description
- Works with Item Sheets - extracts rarity, properties, description
- One-click generation from any sheet

## Installation

### Method 1: Manifest URL (Recommended)

1. In Foundry VTT, go to **Add-on Modules**
2. Click **Install Module**
3. Paste this manifest URL:
   ```
   https://quickbrush.ai/static/foundry-module/module.json
   ```
4. Click **Install**

### Method 2: Manual Installation

1. Download the latest release
2. Extract to your Foundry `Data/modules/quickbrush` directory
3. Restart Foundry VTT
4. Enable the module in your world

## Setup

### 1. Get Your OpenAI API Key

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign up or log in to your account
3. Click **"Create new secret key"**
4. Copy the key (you'll only see it once!)
5. Add credits to your OpenAI account at [OpenAI Billing](https://platform.openai.com/account/billing)

### 2. Configure the Module

1. In Foundry, go to **Game Settings** → **Configure Settings**
2. Click **Module Settings** tab
3. Find **"Quickbrush AI Image Generator (BYOK)"**
4. Configure the following settings:
   - **OpenAI API Key:** Paste your OpenAI API key
   - **Image Model:** Choose between:
     - `GPT-Image-1-Mini` (Default) - Faster and cheaper
     - `GPT-Image-1` - Higher quality
   - **Image Save Folder:** (Optional) Customize the folder name
5. Click **Save Changes**

## Usage

### From Journal Pages

1. Open any journal page
2. Click the **⋮** (controls) button in the header
3. Select one of the Quickbrush options:
   - 🎭 **Character** - For people and humanoids
   - 🌄 **Scene** - For locations and environments
   - 🐉 **Creature** - For monsters and beasts
   - 🗡️ **Item** - For weapons, armor, and objects
4. The dialog opens with journal text auto-extracted!
5. Adjust settings and click **Generate Image**

### From Character Sheets

1. Open any character or NPC sheet
2. Click the **⋮** button in the header
3. Select **Quickbrush**
4. The dialog auto-fills with character details (name, race, class, bio)
5. Check **"Auto-update image"** to set it as the character portrait
6. Click **Generate Image**

### From Item Sheets

1. Open any item sheet
2. Click the **⋮** button in the header
3. Select **Quickbrush: Item**
4. The dialog auto-fills with item details (name, type, rarity, description)
5. Check **"Auto-update image"** to set it as the item icon
6. Click **Generate Image**

### From Journal Directory

1. Go to the **Journal** tab
2. Click the **🎨 Quickbrush** button in the header
3. Manually enter your description
4. Click **Generate Image**

## Generation Options

| Option | Description | Cost Impact |
|--------|-------------|-------------|
| **Type** | Character, Scene, Creature, or Item | None |
| **Description** | What you want to generate (required) | None |
| **Image Name** | Filename for the image | None |
| **Context Prompt** | Additional context for fine-grained control (optional) | None |
| **Quality** | Low/Medium (Standard) or High (HD) | ✅ Higher quality costs more |
| **Aspect Ratio** | Square (1024x1024), Landscape (1792x1024), or Portrait (1024x1792) | ✅ Larger sizes cost more |
| **Reference Images** | Up to 3 reference images (helps refine description) | None |

**Smart Defaults:**
- Scenes default to **Landscape** aspect ratio
- Characters, Creatures, and Items default to **Square**
- All default to **Medium** quality

## Pricing

Since you're using your own OpenAI API key, you pay OpenAI directly based on their pricing:

### Model Pricing

| Model | Quality | Size | Approx. Cost per Image |
|-------|---------|------|------------------------|
| **GPT-Image-1-Mini** (Default) | Standard | 1024x1024 | $0.015 |
| **GPT-Image-1-Mini** | Standard | 1792x1024 or 1024x1792 | $0.030 |
| **GPT-Image-1-Mini** | HD | 1024x1024 | $0.030 |
| **GPT-Image-1-Mini** | HD | 1792x1024 or 1024x1792 | $0.045 |
| **GPT-Image-1** | Standard | 1024x1024 | $0.040 |
| **GPT-Image-1** | Standard | 1792x1024 or 1024x1792 | $0.080 |
| **GPT-Image-1** | HD | 1024x1024 | $0.080 |
| **GPT-Image-1** | HD | 1792x1024 or 1024x1792 | $0.120 |

**Plus:**
- **GPT-4o** (description refinement): $0.001-0.005 per generation

### Example Costs

**Using GPT-Image-1-Mini (Default):**
- Standard Square image: **~$0.015**
- HD Square image: **~$0.030**
- HD Landscape/Portrait image: **~$0.045**

**Using GPT-Image-1:**
- Standard Square image: **~$0.040**
- HD Square image: **~$0.080**
- HD Landscape/Portrait image: **~$0.120**

Check your usage at [OpenAI Platform Usage](https://platform.openai.com/usage).

## Tips & Best Practices

### Writing Good Descriptions

✅ **Do:**
- Include physical details (hair color, clothing, expression)
- Mention the setting and mood
- Be specific about what you want to see
- Use descriptive adjectives

❌ **Don't:**
- Use names (the AI doesn't know characters by name)
- Include story/lore details (focus on appearance)
- Write overly complex instructions

### Using Context Prompts

Context prompts override the description for specific details:
- **"wearing a red cloak"** - Changes outfit
- **"smiling warmly"** - Changes expression
- **"in a dark forest at night"** - Changes scene/mood
- **"battle-damaged and worn"** - Changes condition

### Using Reference Images

Reference images help guide the style and appearance:
- Character portraits from other sources
- Existing Foundry images you want to match
- Art style examples
- Note: DALL-E 3 doesn't directly use reference images, but they help GPT-4o refine the description

## Gallery

All generated images are automatically:
1. Saved to your configured folder (default: `quickbrush-images/`)
2. Added to the **"Quickbrush Gallery"** journal
3. Organized by date (newest first)
4. Tagged with type, quality, and aspect ratio

You can browse your gallery anytime by opening the "Quickbrush Gallery" journal.

## Troubleshooting

### "Please configure your OpenAI API key"

**Solution:** Go to Module Settings and add your OpenAI API key.

### "Failed to generate image: 401"

**Solution:** Your API key is invalid or expired. Get a new one from OpenAI.

### "Failed to generate image: 429"

**Solution:** You've hit OpenAI's rate limit. Wait a minute and try again.

### "Failed to generate image: Billing hard limit reached"

**Solution:** Add more credits to your OpenAI account at [OpenAI Billing](https://platform.openai.com/account/billing).

### Images take a long time to generate

**Normal:** Image generation typically takes 10-60 seconds:
- Step 1: GPT-4o refines your description (~5-10 seconds)
- Step 2: GPT-Image generates the image (~5-50 seconds, depending on model and quality)

You'll see progress notifications during generation.

**Note:** GPT-Image-1-Mini is generally faster than GPT-Image-1.

## Privacy & Security

🔒 **Your API key is stored locally** in Foundry's world settings
🔒 **Your data never goes through Quickbrush servers** - direct to OpenAI
🔒 **All images are generated by OpenAI** (GPT-Image-1 or GPT-Image-1-Mini) according to their [content policy](https://openai.com/policies/usage-policies)
🔒 **Your images are saved locally** to your Foundry data directory

## Support

- **Issues:** [GitHub Issues](https://github.com/jaredraycoleman/quickbrush/issues)
- **Email:** support@quickbrush.ai

## Credits

Created by [Jared Coleman](https://github.com/jaredraycoleman)
Powered by [OpenAI](https://openai.com) (GPT-Image-1, GPT-Image-1-Mini & GPT-4o)
Built for [Foundry VTT](https://foundryvtt.com)

## License

MIT License - See LICENSE file for details

---

**Happy adventuring, and may your campaigns be filled with beautiful art!**
— Wispy Quickbrush 🎨✨
