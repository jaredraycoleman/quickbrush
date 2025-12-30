# Quickbrush CLI

A command-line tool for generating fantasy RPG artwork using OpenAI's image generation API.

## Installation

From the quickbrush monorepo root:

```bash
npm install
```

## Setup

Set your OpenAI API key as an environment variable:

```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

Or create a `.env` file in your project root:

```
OPENAI_API_KEY=sk-your-api-key-here
```

## Usage

### Basic Usage

```bash
# From quickbrush root
npm run cli -- <type> "<description>" [options]

# Or directly
node packages/quickbrush-cli/bin/quickbrush.mjs <type> "<description>" [options]
```

### Types

- `character` - Generate character portraits (default: portrait aspect ratio)
- `creature` - Generate creature art (default: portrait aspect ratio)
- `item` - Generate item art (default: square aspect ratio)
- `scene` - Generate scene/environment art (default: landscape aspect ratio)

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--output <path>` | `-o` | Output file path | `./output.png` |
| `--reference <path>` | `-r` | Reference image (can use multiple times, max 4) | - |
| `--context <prompt>` | `-c` | Context prompt to guide generation | - |
| `--quality <level>` | `-q` | Quality: `low`, `medium`, `high` | `medium` |
| `--aspect <ratio>` | `-a` | Aspect ratio: `square`, `portrait`, `landscape` | varies by type |
| `--model <model>` | `-m` | Model: `gpt-image-1`, `gpt-image-1-mini` | `gpt-image-1` |
| `--interactive` | `-i` | Interactive mode | - |
| `--verbose` | `-v` | Verbose output | - |
| `--help` | `-h` | Show help | - |

### Examples

```bash
# Generate a character portrait
npm run cli -- character "A wise old wizard with a long grey beard and piercing blue eyes" -o wizard.png

# Generate a creature with reference image
npm run cli -- creature "A fierce dragon with emerald scales" -r dragon-sketch.jpg -q high -o dragon.png

# Generate an item with context
npm run cli -- item "An ancient magical staff" -c "glowing with blue arcane energy" -o staff.png

# Generate a landscape scene
npm run cli -- scene "A mystical forest clearing at twilight with glowing mushrooms" -a landscape -o forest.png

# Use multiple reference images
npm run cli -- character "A young elven ranger" -r face-ref.jpg -r outfit-ref.jpg -o ranger.png

# Interactive mode - prompts for all options
npm run cli -- -i
```

## Interactive Mode

Run with `-i` or `--interactive` to be prompted for all options:

```bash
npm run cli -- -i
```

This will guide you through:
1. Selecting the art type
2. Entering a description
3. Adding optional context
4. Specifying reference images
5. Choosing quality and aspect ratio
6. Selecting the model
7. Setting the output path

## Integration with Projects

To use quickbrush in another project:

1. Add quickbrush as a git submodule:
   ```bash
   git submodule add git@github.com:wizzlethorpe/quickbrush.git quickbrush
   ```

2. Install dependencies:
   ```bash
   cd quickbrush && npm install
   ```

3. Run the CLI:
   ```bash
   cd quickbrush && npm run cli -- character "Your description" -o ../output.png
   ```

Or create a wrapper script in your project that calls the CLI.

## API

The CLI uses the `quickbrush-core` library internally. For programmatic usage, you can import the core library directly:

```javascript
import { OpenAIClient, createGenerator } from './quickbrush/packages/quickbrush-core/src/index.js';

const client = new OpenAIClient(process.env.OPENAI_API_KEY);
const generator = createGenerator('character', client);

const description = await generator.getDescription(
  'A wise old wizard',
  'wearing ceremonial robes',
  [] // reference images as base64 data URIs
);

const imageBlob = await generator.generateImage({
  description: description.text,
  model: 'gpt-image-1',
  quality: 'high',
  aspectRatio: 'portrait',
});
```
