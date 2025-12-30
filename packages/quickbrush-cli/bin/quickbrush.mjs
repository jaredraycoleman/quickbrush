#!/usr/bin/env node

/**
 * Quickbrush CLI
 *
 * A command-line tool for generating art using OpenAI's image generation API.
 *
 * Usage:
 *   quickbrush <type> <description> [options]
 *   quickbrush --interactive
 *
 * Types: character, creature, item, scene
 *
 * Options:
 *   -o, --output <path>      Output file path (default: ./output.png)
 *   -r, --reference <path>   Reference image path (can be used multiple times)
 *   -c, --context <prompt>   Context prompt to guide the generation
 *   -q, --quality <level>    Quality level: low, medium, high (default: medium)
 *   -a, --aspect <ratio>     Aspect ratio: square, portrait, landscape (default: portrait for characters, square otherwise)
 *   -m, --model <model>      Model: gpt-image-1, gpt-image-1-mini (default: gpt-image-1)
 *   -i, --interactive        Interactive mode - prompts for all options
 *   -v, --verbose            Verbose output
 *   -h, --help               Show help
 *
 * Environment:
 *   OPENAI_API_KEY           Required. Your OpenAI API key.
 *
 * Examples:
 *   quickbrush character "A wise old wizard with a long grey beard" -o wizard.png
 *   quickbrush creature "A fierce dragon with emerald scales" -r reference.jpg -q high
 *   quickbrush item "An ancient magical staff" --context "glowing with blue energy"
 *   quickbrush scene "A mystical forest clearing at twilight" -a landscape
 *   quickbrush --interactive
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import readline from 'readline';

// Load environment variables from .env file if present
try {
  const dotenv = await import('dotenv');
  dotenv.config();
} catch {
  // dotenv not available, continue without it
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Import quickbrush-core
const corePath = path.join(__dirname, '..', '..', 'quickbrush-core', 'src', 'index.js');
const { OpenAIClient, createGenerator } = await import(`file://${corePath}`);

// Parse command line arguments
function parseArgs(args) {
  const result = {
    type: null,
    description: null,
    output: './output.png',
    references: [],
    context: null,
    quality: 'medium',
    aspect: null,
    model: 'gpt-image-1',
    interactive: false,
    verbose: false,
    help: false,
  };

  let i = 0;
  while (i < args.length) {
    const arg = args[i];

    if (arg === '-h' || arg === '--help') {
      result.help = true;
    } else if (arg === '-i' || arg === '--interactive') {
      result.interactive = true;
    } else if (arg === '-v' || arg === '--verbose') {
      result.verbose = true;
    } else if (arg === '-o' || arg === '--output') {
      result.output = args[++i];
    } else if (arg === '-r' || arg === '--reference') {
      result.references.push(args[++i]);
    } else if (arg === '-c' || arg === '--context') {
      result.context = args[++i];
    } else if (arg === '-q' || arg === '--quality') {
      result.quality = args[++i];
    } else if (arg === '-a' || arg === '--aspect') {
      result.aspect = args[++i];
    } else if (arg === '-m' || arg === '--model') {
      result.model = args[++i];
    } else if (!arg.startsWith('-')) {
      if (!result.type) {
        result.type = arg;
      } else if (!result.description) {
        result.description = arg;
      }
    }
    i++;
  }

  return result;
}

function showHelp() {
  console.log(`
Quickbrush CLI - Generate art using OpenAI's image generation API

Usage:
  quickbrush <type> <description> [options]
  quickbrush --interactive

Types:
  character   Generate character portraits (default: portrait aspect)
  creature    Generate creature art (default: portrait aspect)
  item        Generate item art (default: square aspect)
  scene       Generate scene/environment art (default: landscape aspect)

Options:
  -o, --output <path>      Output file path (default: ./output.png)
  -r, --reference <path>   Reference image path (can be used multiple times, max 4)
  -c, --context <prompt>   Context prompt to guide the generation
  -q, --quality <level>    Quality: low, medium, high (default: medium)
  -a, --aspect <ratio>     Aspect ratio: square, portrait, landscape
  -m, --model <model>      Model: gpt-image-1, gpt-image-1-mini (default: gpt-image-1)
  -i, --interactive        Interactive mode - prompts for all options
  -v, --verbose            Verbose output
  -h, --help               Show this help message

Environment Variables:
  OPENAI_API_KEY           Required. Your OpenAI API key.

Examples:
  quickbrush character "A wise old wizard with a long grey beard" -o wizard.png
  quickbrush creature "A fierce dragon with emerald scales" -r photo.jpg -q high
  quickbrush item "An ancient magical staff" --context "glowing with blue energy"
  quickbrush scene "A mystical forest clearing" -a landscape
  quickbrush -i
`);
}

function createReadlineInterface() {
  return readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
}

async function prompt(rl, question, defaultValue = '') {
  return new Promise((resolve) => {
    const defaultStr = defaultValue ? ` (${defaultValue})` : '';
    rl.question(`${question}${defaultStr}: `, (answer) => {
      resolve(answer.trim() || defaultValue);
    });
  });
}

async function promptChoice(rl, question, choices, defaultValue) {
  const choicesStr = choices.map((c, i) =>
    c === defaultValue ? `[${c}]` : c
  ).join(', ');

  return new Promise((resolve) => {
    rl.question(`${question} (${choicesStr}): `, (answer) => {
      const value = answer.trim().toLowerCase() || defaultValue;
      if (choices.includes(value)) {
        resolve(value);
      } else {
        console.log(`Invalid choice. Using default: ${defaultValue}`);
        resolve(defaultValue);
      }
    });
  });
}

async function runInteractive(options) {
  const rl = createReadlineInterface();

  console.log('\n=== Quickbrush Interactive Mode ===\n');

  try {
    // Type
    options.type = await promptChoice(
      rl,
      'What type of art?',
      ['character', 'creature', 'item', 'scene'],
      'character'
    );

    // Description
    options.description = await prompt(
      rl,
      'Describe what you want to generate',
      ''
    );

    if (!options.description) {
      console.error('Error: Description is required.');
      rl.close();
      process.exit(1);
    }

    // Context
    options.context = await prompt(
      rl,
      'Any additional context or focus? (optional)',
      ''
    ) || null;

    // Reference images
    const refAnswer = await prompt(
      rl,
      'Reference image paths (comma-separated, optional)',
      ''
    );
    if (refAnswer) {
      options.references = refAnswer.split(',').map(r => r.trim()).filter(Boolean);
    }

    // Quality
    options.quality = await promptChoice(
      rl,
      'Quality level',
      ['low', 'medium', 'high'],
      'medium'
    );

    // Aspect ratio
    const defaultAspect = getDefaultAspect(options.type);
    options.aspect = await promptChoice(
      rl,
      'Aspect ratio',
      ['square', 'portrait', 'landscape'],
      defaultAspect
    );

    // Model
    options.model = await promptChoice(
      rl,
      'Model',
      ['gpt-image-1', 'gpt-image-1-mini'],
      'gpt-image-1'
    );

    // Output
    const defaultOutput = generateDefaultFilename(options.type, options.description);
    options.output = await prompt(
      rl,
      'Output file path',
      defaultOutput
    );

    rl.close();
  } catch (err) {
    rl.close();
    throw err;
  }

  return options;
}

function getDefaultAspect(type) {
  switch (type) {
    case 'character':
    case 'creature':
      return 'portrait';
    case 'scene':
      return 'landscape';
    case 'item':
    default:
      return 'square';
  }
}

function generateDefaultFilename(type, description) {
  // Create a slug from the description
  const slug = description
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 30);

  const timestamp = Date.now();
  return `./${type}-${slug}-${timestamp}.png`;
}

function imageToBase64(imagePath) {
  const absolutePath = path.resolve(imagePath);

  if (!fs.existsSync(absolutePath)) {
    throw new Error(`Reference image not found: ${absolutePath}`);
  }

  const imageBuffer = fs.readFileSync(absolutePath);
  const ext = path.extname(imagePath).toLowerCase();

  let mimeType;
  switch (ext) {
    case '.png':
      mimeType = 'image/png';
      break;
    case '.jpg':
    case '.jpeg':
      mimeType = 'image/jpeg';
      break;
    case '.gif':
      mimeType = 'image/gif';
      break;
    case '.webp':
      mimeType = 'image/webp';
      break;
    default:
      mimeType = 'image/png';
  }

  const base64 = imageBuffer.toString('base64');
  return `data:${mimeType};base64,${base64}`;
}

async function main() {
  const args = process.argv.slice(2);
  let options = parseArgs(args);

  if (options.help) {
    showHelp();
    process.exit(0);
  }

  // Check for API key
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    console.error('Error: OPENAI_API_KEY environment variable is required.');
    console.error('Set it in your environment or create a .env file.');
    process.exit(1);
  }

  // Interactive mode
  if (options.interactive) {
    options = await runInteractive(options);
  }

  // Validate required arguments
  if (!options.type) {
    console.error('Error: Type is required (character, creature, item, scene).');
    console.error('Use --help for usage information.');
    process.exit(1);
  }

  if (!options.description) {
    console.error('Error: Description is required.');
    console.error('Use --help for usage information.');
    process.exit(1);
  }

  const validTypes = ['character', 'creature', 'item', 'scene'];
  if (!validTypes.includes(options.type)) {
    console.error(`Error: Invalid type "${options.type}". Must be one of: ${validTypes.join(', ')}`);
    process.exit(1);
  }

  // Set default aspect ratio if not specified
  if (!options.aspect) {
    options.aspect = getDefaultAspect(options.type);
  }

  // Convert reference images to base64
  const referenceImages = [];
  for (const refPath of options.references) {
    try {
      if (options.verbose) {
        console.log(`Loading reference image: ${refPath}`);
      }
      referenceImages.push(imageToBase64(refPath));
    } catch (err) {
      console.error(`Error loading reference image: ${err.message}`);
      process.exit(1);
    }
  }

  if (referenceImages.length > 4) {
    console.error('Error: Maximum 4 reference images allowed.');
    process.exit(1);
  }

  // Initialize client and generator
  const client = new OpenAIClient(apiKey);
  const generator = createGenerator(options.type, client);

  console.log(`\nGenerating ${options.type} art...`);
  if (options.verbose) {
    console.log(`  Description: ${options.description}`);
    console.log(`  Context: ${options.context || '(none)'}`);
    console.log(`  Quality: ${options.quality}`);
    console.log(`  Aspect: ${options.aspect}`);
    console.log(`  Model: ${options.model}`);
    console.log(`  References: ${referenceImages.length}`);
    console.log(`  Output: ${options.output}`);
  }

  try {
    // Step 1: Generate refined description
    console.log('\nStep 1/2: Generating description...');
    const description = await generator.getDescription(
      options.description,
      options.context,
      referenceImages
    );

    if (options.verbose) {
      console.log(`\nRefined description:\n${description.text}\n`);
    }

    // Step 2: Generate image
    console.log('Step 2/2: Generating image...');
    const imageBlob = await generator.generateImage({
      description: description.text,
      referenceImages,
      model: options.model,
      quality: options.quality,
      aspectRatio: options.aspect,
    });

    // Save the image
    const outputPath = path.resolve(options.output);
    const outputDir = path.dirname(outputPath);

    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    // Convert Blob to Buffer and save
    const arrayBuffer = await imageBlob.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    fs.writeFileSync(outputPath, buffer);

    console.log(`\nImage saved to: ${outputPath}`);

  } catch (err) {
    console.error(`\nError: ${err.message}`);
    if (options.verbose && err.stack) {
      console.error(err.stack);
    }
    process.exit(1);
  }
}

main();
