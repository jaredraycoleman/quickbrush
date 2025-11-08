# @quickbrush/core

Shared image generation logic for Quickbrush. Built by Wizzlethorpe Labs.

## Overview

This package contains the core business logic for generating AI-powered fantasy RPG artwork using OpenAI's APIs. Platform-agnostic design supports:

- **Web applications**
- **Foundry VTT modules**
- **Obsidian plugins**
- Any JavaScript/TypeScript project

## Installation

This is a local package in the Quickbrush monorepo. It's consumed by other projects via:

```json
{
  "dependencies": {
    "@quickbrush/core": "file:../packages/quickbrush-core"
  }
}
```

Or bundled directly into browser environments.

## Usage

### ES6 Modules (Recommended)

```javascript
import { OpenAIClient, createGenerator } from '@quickbrush/core';

// Create a client
const client = new OpenAIClient('your-api-key');

// Create a generator for the type you need
const generator = createGenerator('character', client);

// Get a description from text
const description = await generator.getDescription(
  'A brave knight with golden armor',
  'Generate a physical description focusing on their appearance',
  [] // optional reference images
);

// Generate an image
const imageBlob = await generator.generateImage({
  description: description.text,
  referenceImages: [],
  model: 'gpt-image-1-mini',
  quality: 'high',
  aspectRatio: 'square'
});
```

### Browser Global

```javascript
const { OpenAIClient, createGenerator } = window.QuickbrushCore;
```

### CommonJS

```javascript
const { OpenAIClient, createGenerator } = require('@quickbrush/core');
```

## API Reference

### Classes

#### `OpenAIClient`

Handles direct communication with OpenAI's API.

**Constructor:**
- `new OpenAIClient(apiKey: string)`

**Methods:**
- `generateDescription(options)` - Generate a description using GPT-4o
- `generateImage(options)` - Generate an image using OpenAI's API
  - Uses `images/edits` endpoint when reference images are provided
  - Uses `images/generations` endpoint for standard generation without references

#### `ImageGenerator` (Abstract Base Class)

Base class for all generator types.

**Subclasses:**
- `CharacterImageGenerator` - For character portraits
- `SceneImageGenerator` - For environment/scene art
- `CreatureImageGenerator` - For creature/monster art
- `ItemImageGenerator` - For item/object art

### Factory Function

#### `createGenerator(type, openaiClient)`

Creates the appropriate generator instance.

**Parameters:**
- `type`: `'character' | 'scene' | 'creature' | 'item'`
- `openaiClient`: Instance of `OpenAIClient`

**Returns:** Instance of the appropriate generator class

## Development

### Syncing to Consumer Projects

After making changes to the core library, sync it to all consuming projects:

```bash
npm run sync-core
```

This copies the core library to:
- `foundry-module/scripts/quickbrush-core.js`
- `docs/js/quickbrush-core.js`

### File Structure

```
packages/quickbrush-core/
├── package.json
├── README.md
└── src/
    └── index.js  # Main entry point
```

## License

MIT
