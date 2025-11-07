/**
 * Quickbrush Core Library TypeScript Definitions
 */

export class OpenAIClient {
  constructor(apiKey: string);

  generateDescription(options: {
    systemPrompt: string;
    userText: string;
    contextPrompt: string;
    referenceImages?: string[];
  }): Promise<{ text: string }>;

  generateImage(options: {
    prompt: string;
    referenceImages?: string[];
    model?: string;
    size?: string;
    quality?: string;
    background?: string;
  }): Promise<string>;
}

export abstract class ImageGenerator {
  constructor(openaiClient: OpenAIClient);

  defaultImageSize: string;

  getPrompt(description: string): string;
  getSystemPrompt(): string;
  getDefaultContextPrompt(): string;

  getDescription(
    text: string,
    prompt?: string | null,
    referenceImages?: string[]
  ): Promise<{ text: string }>;

  generateImage(options: {
    description: string;
    referenceImages?: string[];
    model?: string;
    imageSize?: string | null;
    quality?: string;
    aspectRatio?: 'square' | 'landscape' | 'portrait';
  }): Promise<Blob>;
}

export class CharacterImageGenerator extends ImageGenerator {}
export class SceneImageGenerator extends ImageGenerator {}
export class CreatureImageGenerator extends ImageGenerator {}
export class ItemImageGenerator extends ImageGenerator {}

export function createGenerator(
  type: 'character' | 'scene' | 'creature' | 'item',
  openaiClient: OpenAIClient
): ImageGenerator;

declare const _default: {
  OpenAIClient: typeof OpenAIClient;
  ImageGenerator: typeof ImageGenerator;
  CharacterImageGenerator: typeof CharacterImageGenerator;
  SceneImageGenerator: typeof SceneImageGenerator;
  CreatureImageGenerator: typeof CreatureImageGenerator;
  ItemImageGenerator: typeof ItemImageGenerator;
  createGenerator: typeof createGenerator;
};

export default _default;
