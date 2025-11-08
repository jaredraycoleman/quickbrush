/**
 * Quickbrush Core Library
 * Reusable image generation logic for multiple platforms
 * Ported from maker.py
 */

/**
 * OpenAI API Client
 * Handles direct communication with OpenAI's API
 */
class OpenAIClient {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseUrl = 'https://api.openai.com/v1';
  }

  /**
   * Generate a description using GPT-4o
   */
  async generateDescription({ systemPrompt, userText, contextPrompt, referenceImages = [] }) {
    const messages = [
      {
        role: 'system',
        content: systemPrompt
      }
    ];

    // Build user message content array
    const userContent = [];

    // Add reference images first if provided
    let imageDescription = 'No reference images provided.';

    if (referenceImages && referenceImages.length > 0) {
      // First, describe the reference images
      const imageContent = referenceImages.map(base64Image => ({
        type: 'image_url',
        image_url: {
          url: base64Image // Already in data URI format
        }
      }));

      try {
        const imageDescResponse = await this._chatCompletion({
          model: 'gpt-4o',
          messages: [
            {
              role: 'system',
              content: 'You are a helpful assistant that generates detailed physical descriptions of provided images.'
            },
            {
              role: 'user',
              content: [
                {
                  type: 'text',
                  text: 'Generate a detailed physical description of the subject of the image.'
                },
                ...imageContent
              ]
            }
          ]
        });

        imageDescription = imageDescResponse.choices[0].message.content || imageDescription;
      } catch (err) {
        console.warn('Failed to describe reference images:', err);
      }
    }

    // Build the prompt JSON structure
    const promptJson = {
      properties: {
        text: {
          type: 'string',
          description: 'Long-form detailed information about the subject (e.g., possibly from a journal entry). May include irrelevant details; focus on physical description.',
          value: userText
        },
        reference_images_description: {
          type: 'string',
          description: 'A detailed physical description of the subject based on the provided reference images. If no reference images were provided, this will be an empty string.',
          value: imageDescription
        },
        prompt: {
          type: 'string',
          description: 'The context prompt for the description. This is what the user wants you to focus on when generating the description. It may even contradict details in the long-form text and/or reference images. Always prioritize this prompt over the long-form text and/or reference images.',
          value: contextPrompt
        }
      }
    };

    messages.push({
      role: 'user',
      content: [
        {
          type: 'text',
          text: JSON.stringify(promptJson)
        }
      ]
    });

    const response = await this._chatCompletion({
      model: 'gpt-4o',
      messages
    });

    if (!response.choices || !response.choices[0]) {
      throw new Error('No response from OpenAI API.');
    }

    const descriptionText = (response.choices[0].message.content || '').trim();

    if (!descriptionText) {
      throw new Error('Parsed description is empty.');
    }

    return { text: descriptionText };
  }

  /**
   * Generate an image using OpenAI's image generation API
   * Uses images/edits endpoint if reference images are provided, otherwise images/generations
   */
  async generateImage({
    prompt,
    referenceImages = [],
    model = 'gpt-image-1-mini',
    size = '1024x1024',
    quality = 'medium',
    background = 'transparent',
  }) {
    // If reference images are provided, use the edits endpoint
    if (referenceImages && referenceImages.length > 0) {
      return await this._imageEdit({
        prompt,
        referenceImages,
        model,
        size,
        quality,
        background
      });
    }

    // Otherwise use the standard generations endpoint
    const params = {
      model,
      prompt,
      size,
      quality,
      background,
      n: 1
    };

    const response = await this._imageGeneration(params);

    if (!response.data || !response.data[0] || !response.data[0].b64_json) {
      throw new Error('No image data returned from OpenAI API.');
    }

    return response.data[0].b64_json;
  }

  /**
   * Internal method for chat completions
   */
  async _chatCompletion(params) {
    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify(params)
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: { message: response.statusText } }));
      throw new Error(`OpenAI API error: ${error.error?.message || response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Internal method for image generation
   */
  async _imageGeneration(params) {
    const response = await fetch(`${this.baseUrl}/images/generations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify(params)
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: { message: response.statusText } }));
      throw new Error(`OpenAI API error: ${error.error?.message || response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Internal method for image editing with reference images
   * Uses multipart/form-data to send reference images
   */
  async _imageEdit({ prompt, referenceImages, model, size, quality, background }) {
    const formData = new FormData();

    formData.append('model', model);
    formData.append('prompt', prompt);
    formData.append('size', size);
    formData.append('quality', quality);
    formData.append('background', background);
    formData.append('n', '1');

    // Convert base64 data URIs to Blobs and add as form fields
    for (let i = 0; i < referenceImages.length; i++) {
      const base64Image = referenceImages[i];

      // Extract the base64 data from data URI (remove "data:image/png;base64," prefix)
      const base64Data = base64Image.split(',')[1] || base64Image;

      // Convert base64 to binary
      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let j = 0; j < binaryString.length; j++) {
        bytes[j] = binaryString.charCodeAt(j);
      }

      // Create a Blob from the binary data
      const blob = new Blob([bytes], { type: 'image/png' });

      // Add to form data as 'image' (OpenAI expects array of images with field name 'image')
      formData.append('image', blob, `reference_${i}.png`);
    }

    const response = await fetch(`${this.baseUrl}/images/edits`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`
        // Don't set Content-Type - browser will set it with boundary for multipart/form-data
      },
      body: formData
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: { message: response.statusText } }));
      throw new Error(`OpenAI API error: ${error.error?.message || response.statusText}`);
    }

    const result = await response.json();

    // gpt-image-1 and gpt-image-1-mini return base64 by default
    if (!result.data || !result.data[0] || !result.data[0].b64_json) {
      throw new Error('No image data returned from OpenAI API.');
    }

    return result.data[0].b64_json;
  }
}

/**
 * Base Image Generator class
 * Abstract base for all generator types
 */
class ImageGenerator {
  constructor(openaiClient) {
    this.client = openaiClient;
    this.defaultImageSize = '1024x1024';
  }

  /**
   * Get the prompt for image generation
   * Must be implemented by subclasses
   */
  getPrompt(description) {
    throw new Error('getPrompt must be implemented by subclass');
  }

  /**
   * Get the system prompt for description extraction
   * Must be implemented by subclasses
   */
  getSystemPrompt() {
    throw new Error('getSystemPrompt must be implemented by subclass');
  }

  /**
   * Get the default context prompt
   * Must be implemented by subclasses
   */
  getDefaultContextPrompt() {
    throw new Error('getDefaultContextPrompt must be implemented by subclass');
  }

  /**
   * Extract a description from the provided text
   */
  async getDescription(text, prompt = null, referenceImages = []) {
    const contextPrompt = prompt || this.getDefaultContextPrompt();
    const systemPrompt = this.getSystemPrompt();

    return await this.client.generateDescription({
      systemPrompt,
      userText: text,
      contextPrompt,
      referenceImages
    });
  }

  /**
   * Generate an image based on the description
   */
  async generateImage({
    description,
    referenceImages = [],
    model = 'gpt-image-1-mini',
    imageSize = null,
    quality = 'medium',
    aspectRatio = 'square'
  }) {
    // Use default image size if none provided
    if (!imageSize) {
      imageSize = this.defaultImageSize;
    }

    // Map aspect ratio to size
    const size = this._mapAspectRatioToSize(aspectRatio);

    // Get the full prompt
    const prompt = this.getPrompt(description);

    // Generate the image
    const base64Image = await this.client.generateImage({
      prompt,
      referenceImages,
      model,
      size,
      quality: quality,
    });

    // Convert base64 to Blob
    const binaryString = atob(base64Image);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    return new Blob([bytes], { type: 'image/png' });
  }

  /**
   * Map aspect ratio to OpenAI size format
   */
  _mapAspectRatioToSize(aspectRatio) {
    const sizeMap = {
      'square': '1024x1024',
      'landscape': '1536x1024',
      'portrait': '1024x1536'
    };
    return sizeMap[aspectRatio] || '1024x1024';
  }

}

/**
 * Character Image Generator
 */
class CharacterImageGenerator extends ImageGenerator {
  getDefaultContextPrompt() {
    return 'Generate a physical description of a character.';
  }

  getSystemPrompt() {
    return `You are a helpful assistant that creates short but detailed character descriptions based on the prompt provided and a general description of the character. Always give preference to the prompt over the general description (e.g., the prompt might ask them to wear a specific outfit or have a certain hairstyle while the general description describes them as typically wearing a different outfit). This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. Include any relevant physical details that someone would need to accurately visualize the character. Focus on the physical description and do not include any names (even the character's name), personality traits, lore, etc.`;
  }

  getPrompt(description) {
    return `Highly stylized digital concept art profile of ${description}. Rendered in a fantasy-steampunk illustration style inspired by graphic novel and fantasy RPG character art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. Facial features are expressive and detailed, with textured hair and stylized lighting that adds depth and mood. The background fades into negative space, as if the character is emerging from the page. The character is looking directly at the viewer. The background is white. The character is centered in the frame, with their head and shoulders fitting within the image.`;
  }
}

/**
 * Scene Image Generator
 */
class SceneImageGenerator extends ImageGenerator {
  getDefaultContextPrompt() {
    return '';
  }

  getSystemPrompt() {
    return `You are a helpful assistant that creates short but detailed scene descriptions based on the prompt provided and a general description of the scene. Always give preference to the prompt over the general description (e.g., the prompt might ask for a specific setting or time of day while the general description describes a different setting). This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. Focus on the physical description and do not include any names, personality traits, lore, etc.`;
  }

  getPrompt(description) {
    const specific = description ? ` featuring ${description}` : '';
    return `Highly stylized digital concept art${specific}. Rendered in a fantasy illustration style inspired by graphic novel and fantasy RPG scene art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. The background fades into negative space, as if the scene is emerging from the page. The scene is from a ground, first-person perspective, with a wide view of the environment. Focus on the physical description and do not include any names, personality traits, lore, etc. The background is white.`;
  }
}

/**
 * Creature Image Generator
 */
class CreatureImageGenerator extends ImageGenerator {
  getDefaultContextPrompt() {
    return 'Generate a physical description of a creature.';
  }

  getSystemPrompt() {
    return `You are a helpful assistant that creates short but detailed creature descriptions based on the prompt provided and a general description of the creature's appearance. Always give preference to the prompt over the general description (e.g., the prompt might ask them to have a specific feature or color while the general description describes them as typically having different features). This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. Focus on the physical description and do not include any names (even the creature's name), personality traits, lore, etc.`;
  }

  getPrompt(description) {
    return `Highly stylized digital concept art profile of ${description}. Rendered in a fantasy illustration style inspired by graphic novel and fantasy RPG creature art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. Facial features are expressive and detailed, with textured skin/fur/scales and stylized lighting that adds depth and mood. The background fades into negative space, as if the creature is emerging from the page. The creature is looking directly at the viewer. The background is white. The creature is centered in the frame, with their head and shoulders fitting within the image.`;
  }
}

/**
 * Item Image Generator
 */
class ItemImageGenerator extends ImageGenerator {
  getDefaultContextPrompt() {
    return 'Generate a physical description of the item.';
  }

  getSystemPrompt() {
    return `You are a helpful assistant that creates short but detailed item descriptions based on the prompt provided and a general description of the item's appearance. Always give preference to the prompt over the general description (e.g., the prompt might ask for a specific material or design while the general description describes it as typically having different features). This will be used as a prompt for generating an image, so be as consistent and descriptive as possible. Only relate the physical description of the item and do not include any names (even of the item itself), lore, personality, etc.`;
  }

  getPrompt(description) {
    return `Highly stylized digital concept art of ${description}. Rendered in a fantasy illustration style inspired by graphic novel and fantasy RPG item art with bold, clean line work, muted yet rich colors, and dramatic cel-shading. The item is detailed and textured, with stylized lighting that adds depth and mood. The background fades into negative space, as if the item is emerging from the page. The item is centered in the frame, fitting within the image with space around it. The background is white.`;
  }
}

/**
 * Factory function to create the appropriate generator
 */
function createGenerator(type, openaiClient) {
  switch (type) {
    case 'character':
      return new CharacterImageGenerator(openaiClient);
    case 'scene':
      return new SceneImageGenerator(openaiClient);
    case 'creature':
      return new CreatureImageGenerator(openaiClient);
    case 'item':
      return new ItemImageGenerator(openaiClient);
    default:
      throw new Error(`Unknown generator type: ${type}`);
  }
}

// ES6 Module exports (for dynamic import)
export {
  OpenAIClient,
  ImageGenerator,
  CharacterImageGenerator,
  SceneImageGenerator,
  CreatureImageGenerator,
  ItemImageGenerator,
  createGenerator
};

// Also export as default for convenience
export default {
  OpenAIClient,
  ImageGenerator,
  CharacterImageGenerator,
  SceneImageGenerator,
  CreatureImageGenerator,
  ItemImageGenerator,
  createGenerator
};

// Browser global (for backwards compatibility with script tag usage)
if (typeof window !== 'undefined') {
  window.QuickbrushCore = {
    OpenAIClient,
    ImageGenerator,
    CharacterImageGenerator,
    SceneImageGenerator,
    CreatureImageGenerator,
    ItemImageGenerator,
    createGenerator
  };
}
