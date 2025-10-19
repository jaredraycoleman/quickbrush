/**
 * Quickbrush AI Image Generator for Foundry VTT
 * Generate fantasy RPG artwork using Quickbrush API
 */

const MODULE_ID = 'quickbrush';
const API_ENDPOINT = 'https://quickbrush.online/api';

/**
 * Quickbrush API Client
 */
class QuickbrushAPI {
  constructor() {
    this.apiKey = game.settings.get(MODULE_ID, 'apiKey');
    this.apiUrl = game.settings.get(MODULE_ID, 'apiUrl') || API_ENDPOINT;
  }

  /**
   * Generate an image using Quickbrush API
   */
  async generateImage({ text, prompt = '', generation_type = 'character', quality = 'medium', aspect_ratio = 'square', reference_image_paths = [] }) {
    if (!this.apiKey) {
      throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.NoApiKey'));
    }

    const requestBody = {
      text,
      prompt,
      generation_type,
      quality,
      aspect_ratio,
      reference_image_paths
    };

    const response = await fetch(`${this.apiUrl}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));

      console.error('Quickbrush API error:', response.status, error);

      // Handle specific error types
      if (response.status === 429) {
        throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.RateLimit'));
      } else if (response.status === 402) {
        throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.InsufficientBrushstrokes'));
      } else if (response.status === 422) {
        // Validation error - extract meaningful message
        let message = 'Validation failed';
        if (Array.isArray(error.detail)) {
          // FastAPI validation errors are arrays
          message = error.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
        } else if (error.detail) {
          message = typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail);
        }
        console.error('Validation errors:', error.detail);
        throw new Error(`Validation error: ${message}`);
      }

      const errorMsg = error.detail || error.message || (typeof error === 'string' ? error : JSON.stringify(error)) || 'Unknown error';
      throw new Error(errorMsg);
    }

    return await response.json();
  }

  /**
   * Download image from Quickbrush
   */
  async downloadImage(imageUrl) {
    const response = await fetch(imageUrl, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`
      }
    });
    if (!response.ok) {
      throw new Error(`Failed to download image: ${response.statusText}`);
    }
    return await response.blob();
  }

  /**
   * Get rate limit status
   */
  async getRateLimitStatus() {
    if (!this.apiKey) return null;

    try {
      const response = await fetch(`${this.apiUrl}/rate-limit`, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`
        }
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (err) {
      console.warn('Failed to get rate limit status:', err);
    }

    return null;
  }

  /**
   * Get all generations from library
   */
  async getGenerations(limit = 100) {
    if (!this.apiKey) {
      throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.NoApiKey'));
    }

    const response = await fetch(`${this.apiUrl}/generations?limit=${limit}`, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch generations: ${response.statusText}`);
    }

    return await response.json();
  }
}

/**
 * Image Generation Dialog
 */
class QuickbrushDialog extends FormApplication {
  constructor(options = {}) {
    super({}, options);
    this.data = options.data || {};
    this.referenceImages = options.data?.referenceImages || [];
    this.targetDocument = options.targetDocument || null; // Actor or Item to update
  }

  static get defaultOptions() {
    return foundry.utils.mergeObject(super.defaultOptions, {
      id: 'quickbrush-dialog',
      title: game.i18n.localize('QUICKBRUSH.Dialog.Title'),
      template: 'modules/quickbrush/templates/generate-dialog.hbs',
      width: 600,
      height: 700,
      classes: ['quickbrush-dialog'],
      closeOnSubmit: false,
      submitOnChange: false,
      submitOnClose: false,
      resizable: true
    });
  }

  getData() {
    // Manually create the options arrays since i18n.localize returns the full nested object
    const types = [
      { key: 'character', label: game.i18n.localize('QUICKBRUSH.Dialog.Types.character') },
      { key: 'scene', label: game.i18n.localize('QUICKBRUSH.Dialog.Types.scene') },
      { key: 'creature', label: game.i18n.localize('QUICKBRUSH.Dialog.Types.creature') },
      { key: 'item', label: game.i18n.localize('QUICKBRUSH.Dialog.Types.item') }
    ];

    const qualities = [
      { key: 'low', label: game.i18n.localize('QUICKBRUSH.Dialog.Qualities.low') },
      { key: 'medium', label: game.i18n.localize('QUICKBRUSH.Dialog.Qualities.medium') },
      { key: 'high', label: game.i18n.localize('QUICKBRUSH.Dialog.Qualities.high') }
    ];

    const aspectRatios = [
      { key: 'square', label: game.i18n.localize('QUICKBRUSH.Dialog.AspectRatios.square') },
      { key: 'landscape', label: game.i18n.localize('QUICKBRUSH.Dialog.AspectRatios.landscape') },
      { key: 'portrait', label: game.i18n.localize('QUICKBRUSH.Dialog.AspectRatios.portrait') }
    ];

    return {
      text: this.data.text || '',
      prompt: this.data.prompt || '',
      generation_type: this.data.generation_type || 'character',
      quality: this.data.quality || 'medium',
      aspect_ratio: this.data.aspect_ratio || 'square',
      referenceImages: this.referenceImages,
      targetDocument: this.targetDocument,
      targetName: this.targetDocument?.name || null,
      types,
      qualities,
      aspectRatios
    };
  }

  activateListeners(html) {
    super.activateListeners(html);

    // Auto-select aspect ratio based on generation type
    html.find('select[name="generation_type"]').on('change', (event) => {
      const type = event.target.value;
      const aspectRatioSelect = html.find('select[name="aspect_ratio"]');

      if (type === 'scene') {
        aspectRatioSelect.val('landscape');
      } else {
        aspectRatioSelect.val('square');
      }
    });

    // Reference image picker buttons
    html.find('.add-reference-image').on('click', (event) => {
      event.preventDefault();
      this._pickReferenceImage();
    });

    // Remove reference image buttons
    html.find('.remove-reference-image').on('click', (event) => {
      event.preventDefault();
      const index = $(event.currentTarget).data('index');
      this.referenceImages.splice(index, 1);
      this.render();
    });
  }

  async _pickReferenceImage() {
    const fp = new FilePicker({
      type: 'image',
      callback: (path) => {
        if (this.referenceImages.length < 3) {
          this.referenceImages.push(path);
          this.render();
        } else {
          ui.notifications.warn('Maximum 3 reference images allowed', { permanent: false });
        }
      }
    });
    fp.browse();
  }

  async _updateObject(event, formData) {
    event.preventDefault();

    // Validate
    if (!formData.text || !formData.text.trim()) {
      ui.notifications.warn('Please provide a description for your image.');
      return;
    }

    const api = new QuickbrushAPI();

    try {
      // Show progress notification (permanent)
      ui.notifications.info(game.i18n.localize('QUICKBRUSH.Notifications.Generating'), { permanent: true });

      // Close the dialog immediately so user can continue working
      this.close();

      // Add reference images to formData
      formData.reference_image_paths = this.referenceImages || [];

      // Generate image
      const result = await api.generateImage(formData);

      // Download image - construct full URL if relative
      let imageUrl = result.image_url;
      if (imageUrl.startsWith('/')) {
        // Remove /api from apiUrl if it exists, since result.image_url already includes /api
        const baseUrl = api.apiUrl.replace(/\/api$/, '');
        imageUrl = `${baseUrl}${imageUrl}`;
      }
      const imageBlob = await api.downloadImage(imageUrl);

      // Save to Foundry
      const folder = await QuickbrushGallery.getOrCreateFolder();
      const filename = `quickbrush-${result.generation_id}.webp`;
      const file = new File([imageBlob], filename, { type: 'image/webp' });

      const uploadResult = await FilePicker.upload('data', folder, file);

      // Update gallery
      await QuickbrushGallery.addToGallery({
        imageUrl: uploadResult.path,
        type: formData.generation_type,
        description: formData.text,
        prompt: formData.prompt,
        quality: formData.quality,
        aspectRatio: formData.aspect_ratio,
        generationId: result.generation_id,
        refinedDescription: result.refined_description
      });

      // Auto-update target document image if requested
      if (this.targetDocument && formData.auto_update_image) {
        try {
          await this.targetDocument.update({ img: uploadResult.path });
          ui.notifications.info(
            `Image generated and set as ${this.targetDocument.documentName} image for "${this.targetDocument.name}"!`,
            { permanent: true }
          );
        } catch (err) {
          console.error('Failed to update document image:', err);
          ui.notifications.warn(`Image generated but failed to update ${this.targetDocument.documentName} image.`, { permanent: true });
        }
      } else {
        // Success! Show permanent notification
        ui.notifications.info(
          `Image generated and saved successfully to ${folder}! View it in the Quickbrush Gallery journal.`,
          { permanent: true }
        );
      }

    } catch (error) {
      console.error('Quickbrush generation error:', error);
      ui.notifications.error(
        game.i18n.format('QUICKBRUSH.Notifications.Error', { error: error.message }),
        { permanent: true }
      );
    }
  }
}

/**
 * Gallery Manager
 */
class QuickbrushGallery {
  static GALLERY_NAME = 'Quickbrush Gallery';
  static ABOUT_PAGE_NAME = 'About Quickbrush';

  /**
   * Get the About page content
   */
  static getAboutPageContent() {
    return `
      <div style="max-width: 800px; margin: 0 auto;">
        <h1 style="text-align: center; font-size: 2em; margin-bottom: 0.5em;">
          🎨 Welcome to Quickbrush! 🎨
        </h1>

        <p style="font-style: italic; font-size: 1.1em;">
          <strong>Greetings, dear adventurer!</strong>
        </p>
        <p>
          I'm <strong>Wispy Quickbrush</strong>, halfling artist extraordinaire and your magical companion in creating breathtaking artwork for your campaigns! With a flick of my enchanted brush and a sprinkle of arcane artistry, I can bring your characters, creatures, items, and scenes to life faster than a wizard can say "prestidigitation!"
        </p>
        <p>
          Whether you need a portrait of a noble paladin, a fearsome dragon, or a mysterious magical artifact, I'm here to help paint your imagination onto the canvas of reality. Well... digital reality, at least! 🖌️✨
        </p>

        <h2>📖 How to Use Quickbrush</h2>

        <h3>🔑 First Things First: Setting Up Your API Key</h3>
        <ol>
          <li>Visit <a href="https://quickbrush.online" target="_blank">quickbrush.online</a> and create an account</li>
          <li>Copy your API key from your account dashboard</li>
          <li>In Foundry VTT, go to <strong>Settings</strong> → <strong>Configure Settings</strong> → <strong>Module Settings</strong></li>
          <li>Find <strong>Quickbrush</strong> and paste your API key in the <strong>API Key</strong> field</li>
          <li>Click <strong>Save Changes</strong> and you're ready to create!</li>
        </ol>

        <h3>🎭 Generating Images</h3>
        <p>Quickbrush integrates seamlessly throughout Foundry VTT! You can generate images from:</p>

        <h4>📓 Journal Pages</h4>
        <p>Open any journal page, click the <strong>⋮</strong> (controls) button, and select one of the Quickbrush options (Character, Scene, Creature, or Item). I'll automatically extract the text from your journal to use as a description!</p>

        <h4>👤 Character Sheets</h4>
        <p>Open any character or NPC sheet, click the <strong>⋮</strong> button, and select <strong>Quickbrush</strong>. I'll extract their name, race, class, description, and more to create the perfect portrait!</p>

        <h4>🗡️ Item Sheets</h4>
        <p>Open any item sheet, click the <strong>⋮</strong> button, and select <strong>Quickbrush</strong>. I'll use the item's name, type, rarity, and description to paint it for you!</p>

        <h4>📚 Journal Directory</h4>
        <p>Click the <strong>🎨 Quickbrush</strong> button in the Journal tab to open the generation dialog from anywhere!</p>

        <h3>🖼️ Generation Options</h3>
        <ul>
          <li><strong>Generation Type:</strong> Choose Character, Scene, Creature, or Item to guide my artistic style</li>
          <li><strong>Description:</strong> Tell me what you want painted! The more details, the better</li>
          <li><strong>Prompt (Optional):</strong> Add mood, lighting, pose, or artistic direction</li>
          <li><strong>Quality:</strong> Low (fast & cheap), Medium (balanced), or High (detailed & beautiful)</li>
          <li><strong>Aspect Ratio:</strong> Square, Landscape, or Portrait</li>
          <li><strong>Reference Images:</strong> Upload up to 3 reference images to guide the style</li>
          <li><strong>Auto-Update:</strong> When generating from a character/item sheet, check this to automatically set the image</li>
        </ul>

        <h3>📸 Your Gallery</h3>
        <p>All your generated images are automatically saved to this journal's <strong>Images</strong> page! You can browse your artistic collection, copy images to use elsewhere, or just admire my handiwork. 😊</p>

        <p>Use the <strong>🔄 Quickbrush Sync</strong> button in the Journal tab to sync your online library with Foundry!</p>

        <h2>⚠️ Important Information</h2>

        <h3>🤖 AI-Powered Art</h3>
        <p>Quickbrush uses artificial intelligence to generate images based on your descriptions. While I do my best to create exactly what you envision, AI-generated art can sometimes be... creative! You might occasionally get unexpected results, unusual anatomy, or mysterious extra fingers. That's just part of the magical chaos! 🎲</p>

        <p><strong>Please note:</strong> Generated images are subject to the content policies of our AI provider. Keep your prompts family-friendly and in line with the heroic spirit of adventure!</p>

        <h3>💎 Brushstrokes & Pricing</h3>
        <p>Each generation consumes <strong>brushstrokes</strong> from your Quickbrush account:</p>
        <ul>
          <li><strong>Low Quality:</strong> Fewer brushstrokes, faster generation</li>
          <li><strong>Medium Quality:</strong> Balanced cost and quality</li>
          <li><strong>High Quality:</strong> More brushstrokes, stunning detail</li>
        </ul>
        <p>Check your brushstrokes balance at <a href="https://quickbrush.online" target="_blank">quickbrush.online</a>!</p>

        <hr style="margin: 2em 0;">

        <p style="text-align: center; font-style: italic;">
          <strong>Happy adventuring, and may your campaigns be filled with beautiful art!</strong>
        </p>
        <p style="text-align: center;">
          — Wispy Quickbrush 🎨✨
        </p>
        <p style="text-align: center; font-size: 0.9em; margin-top: 1.5em;">
          Quickbrush Module v1.0.1 | <a href="https://quickbrush.online" target="_blank">quickbrush.online</a>
        </p>
      </div>
    `;
  }

  /**
   * Get or create the quickbrush-images folder
   */
  static async getOrCreateFolder() {
    const folderName = game.settings.get(MODULE_ID, 'saveFolder') || 'quickbrush-images';
    const source = 'data';

    try {
      // Check if folder exists
      const browse = await FilePicker.browse(source, folderName);
      return folderName;
    } catch (err) {
      // Folder doesn't exist, create it
      await FilePicker.createDirectory(source, folderName);
      return folderName;
    }
  }

  /**
   * Get or create the Quickbrush Gallery journal
   */
  static async getOrCreateGalleryJournal() {
    let journal = game.journal.find(j => j.name === this.GALLERY_NAME);

    if (!journal) {
      journal = await JournalEntry.create({
        name: this.GALLERY_NAME
      });
    }

    // Ensure About page exists
    await this.ensureAboutPage(journal);

    return journal;
  }

  /**
   * Ensure the About page exists in the gallery
   */
  static async ensureAboutPage(journal) {
    // Check if About page already exists
    let aboutPage = journal.pages.find(p => p.name === this.ABOUT_PAGE_NAME);

    console.log('Quickbrush | Ensuring About page exists:', aboutPage ? 'found' : 'not found');

    if (!aboutPage) {
      // Create the About page
      const pages = await journal.createEmbeddedDocuments('JournalEntryPage', [{
        name: this.ABOUT_PAGE_NAME,
        type: 'text',
        text: {
          content: this.getAboutPageContent(),
          format: CONST.JOURNAL_ENTRY_PAGE_FORMATS.HTML
        },
        sort: 0 // Make it the first page
      }]);
      aboutPage = pages[0];
      console.log('Quickbrush | Created About page');
    } else {
      // Update existing About page content (in case we've updated the text)
      await aboutPage.update({
        'text.content': this.getAboutPageContent()
      });
      console.log('Quickbrush | Updated About page');
    }

    return aboutPage;
  }

  /**
   * Add an image to the gallery
   */
  static async addToGallery({ imageUrl, type, description, prompt, quality, aspectRatio, generationId, refinedDescription }) {
    const journal = await this.getOrCreateGalleryJournal();
    const date = new Date().toLocaleString();

    const template = game.i18n.localize('QUICKBRUSH.Gallery.EntryTemplate');
    const entry = template
      .replace('{type}', type.charAt(0).toUpperCase() + type.slice(1))
      .replace('{date}', date)
      .replace('{description}', description)
      .replace('{quality}', quality.charAt(0).toUpperCase() + quality.slice(1))
      .replace('{aspectRatio}', aspectRatio)
      .replace('{imageUrl}', imageUrl);

    // Get first page or create one
    let page = journal.pages.contents[0];
    if (!page) {
      page = await journal.createEmbeddedDocuments('JournalEntryPage', [{
        name: 'Images',
        type: 'text',
        text: { content: '' }
      }]);
      page = page[0];
    }

    // Prepend new entry to existing content
    const currentContent = page.text.content || '';
    await page.update({
      'text.content': entry + currentContent
    });

    ui.notifications.info(game.i18n.localize('QUICKBRUSH.Notifications.GalleryUpdated'));
  }

  /**
   * Sync library images to gallery
   * Downloads missing images and adds them to the gallery
   */
  static async syncFromLibrary() {
    ui.notifications.info('Syncing Quickbrush library...');

    try {
      const api = new QuickbrushAPI();
      const folder = await this.getOrCreateFolder();
      const journal = await this.getOrCreateGalleryJournal();

      // Get first page or create one
      let page = journal.pages.contents[0];
      if (!page) {
        const pages = await journal.createEmbeddedDocuments('JournalEntryPage', [{
          name: 'Images',
          type: 'text',
          text: { content: '', format: CONST.JOURNAL_ENTRY_PAGE_FORMATS.HTML }
        }]);
        page = pages[0];
      }

      const currentContent = page.text.content || '';

      // Fetch all generations from API
      const response = await api.getGenerations(100);
      const generations = response.generations || [];

      if (generations.length === 0) {
        ui.notifications.info('No images found in library');
        return;
      }

      let addedCount = 0;

      // Process each generation (in reverse so newest are at top)
      for (const gen of generations.reverse()) {
        const generationId = gen.id;

        // Skip if already in gallery (check by generation_id in HTML)
        if (currentContent.includes(`quickbrush-${generationId}`)) {
          continue;
        }

        try {
          // Download image - construct full URL if relative
          let imageUrl = gen.image_url;
          if (imageUrl.startsWith('/')) {
            // Remove /api from apiUrl if it exists, since gen.image_url already includes /api
            const baseUrl = api.apiUrl.replace(/\/api$/, '');
            imageUrl = `${baseUrl}${imageUrl}`;
          }
          const imageBlob = await api.downloadImage(imageUrl);

          // Save to Foundry
          const filename = `quickbrush-${generationId}.webp`;
          const file = new File([imageBlob], filename, { type: 'image/webp' });
          const uploadResult = await FilePicker.upload('data', folder, file);

          // Add to gallery (prepend so it maintains chronological order)
          const template = game.i18n.localize('QUICKBRUSH.Gallery.EntryTemplate');
          const entry = template
            .replace('{type}', (gen.generation_type || 'unknown').charAt(0).toUpperCase() + (gen.generation_type || 'unknown').slice(1))
            .replace('{date}', new Date(gen.created_at).toLocaleString())
            .replace('{description}', gen.user_text || 'No description')
            .replace('{quality}', (gen.quality || 'medium').charAt(0).toUpperCase() + (gen.quality || 'medium').slice(1))
            .replace('{aspectRatio}', 'N/A')
            .replace('{imageUrl}', uploadResult.path);

          // Prepend to gallery
          const updatedContent = entry + (page.text.content || '');
          await page.update({ 'text.content': updatedContent });

          addedCount++;
        } catch (err) {
          console.error(`Failed to sync generation ${generationId}:`, err);
        }
      }

      if (addedCount > 0) {
        ui.notifications.info(`Synced ${addedCount} image${addedCount > 1 ? 's' : ''} from library`);
      } else {
        ui.notifications.info('Gallery is already up to date');
      }

    } catch (error) {
      console.error('Failed to sync library:', error);
      ui.notifications.error(`Failed to sync library: ${error.message}`);
    }
  }
}

/**
 * Helper to extract text from currently visible journal pages
 */
function extractVisibleJournalText(html) {
  const $html = html instanceof jQuery ? html : $(html);
  let textContent = '';

  // Find all visible journal page articles
  const $visiblePages = $html.find('article.journal-entry-page');

  console.log('Quickbrush | Found visible pages:', $visiblePages.length);

  if ($visiblePages.length > 0) {
    // Get text from all visible pages
    $visiblePages.each(function() {
      const pageContent = $(this).find('.journal-page-content');
      if (pageContent.length > 0) {
        // Get the text content, stripping HTML
        const text = pageContent.text();
        textContent += text + ' ';
      }
    });

    // Limit to reasonable length
    textContent = textContent.substring(0, 4000).trim();
  }

  return textContent;
}

/**
 * Module Initialization
 */
Hooks.once('init', () => {
  console.log('Quickbrush | Initializing module');

  // Register settings
  game.settings.register(MODULE_ID, 'apiKey', {
    name: game.i18n.localize('QUICKBRUSH.Settings.ApiKey.Name'),
    hint: game.i18n.localize('QUICKBRUSH.Settings.ApiKey.Hint'),
    scope: 'world',
    config: true,
    type: String,
    default: ''
  });

  game.settings.register(MODULE_ID, 'apiUrl', {
    name: game.i18n.localize('QUICKBRUSH.Settings.ApiUrl.Name'),
    hint: game.i18n.localize('QUICKBRUSH.Settings.ApiUrl.Hint'),
    scope: 'world',
    config: true,
    type: String,
    default: API_ENDPOINT
  });

  game.settings.register(MODULE_ID, 'saveFolder', {
    name: game.i18n.localize('QUICKBRUSH.Settings.SaveFolder.Name'),
    hint: game.i18n.localize('QUICKBRUSH.Settings.SaveFolder.Hint'),
    scope: 'world',
    config: true,
    type: String,
    default: 'quickbrush-images'
  });

  // Register a hidden setting to track if we've shown the About page
  game.settings.register(MODULE_ID, 'aboutPageShown', {
    scope: 'world',
    config: false,
    type: Boolean,
    default: false
  });
});

Hooks.once('ready', async () => {
  console.log('Quickbrush | Module ready');

  // Show the About page on first launch (only for GMs)
  if (game.user.isGM) {
    const aboutPageShown = game.settings.get(MODULE_ID, 'aboutPageShown');

    if (!aboutPageShown) {
      console.log('Quickbrush | First launch detected, showing About page');

      // Create/get the gallery journal
      const journal = await QuickbrushGallery.getOrCreateGalleryJournal();

      // Get the About page
      const aboutPage = journal.pages.find(p => p.name === QuickbrushGallery.ABOUT_PAGE_NAME);

      if (aboutPage) {
        // Show the journal with the About page
        journal.sheet.render(true, { pageId: aboutPage.id });

        // Mark that we've shown the About page
        await game.settings.set(MODULE_ID, 'aboutPageShown', true);

        // Show a friendly notification
        ui.notifications.info('Welcome to Quickbrush! 🎨 Check out the About page to get started!', { permanent: true });
      }
    }
  }
});

/**
 * Add Quickbrush options to journal sheet controls dropdown
 */
Hooks.on('renderJournalEntrySheet', (app, html) => {
  console.log('Quickbrush | Rendering journal sheet');
  if (!game.user.isGM) return;

  // In V13, html might be an HTMLElement, not jQuery
  const $html = html instanceof jQuery ? html : $(html);

  // Find the controls dropdown menu
  const $menu = $html.find('menu.controls-dropdown');

  console.log('Quickbrush | Controls menu found:', $menu.length > 0);

  if ($menu.length === 0) return;

  // Add Quickbrush submenu items
  const generationTypes = [
    { type: 'character', label: '🎭 Character', icon: 'fa-user' },
    { type: 'scene', label: '🌄 Scene', icon: 'fa-image' },
    { type: 'creature', label: '🐉 Creature', icon: 'fa-dragon' },
    { type: 'item', label: '🗡️ Item', icon: 'fa-gem' }
  ];

  generationTypes.forEach(({ type, label, icon }) => {
    const menuItem = $(`
      <li class="header-control" data-action="quickbrush-${type}">
        <button type="button" class="control">
          <i class="control-icon fa-fw fa-solid ${icon}"></i>
          <span class="control-label">Quickbrush: ${label}</span>
        </button>
      </li>
    `);

    menuItem.find('button').on('click', () => {
      const textContent = extractVisibleJournalText($html);

      // Extract first 3 images from journal
      const referenceImages = [];
      const $visiblePages = $html.find('article.journal-entry-page');
      $visiblePages.each(function() {
        if (referenceImages.length < 3) {
          $(this).find('.journal-page-content img').each(function() {
            if (referenceImages.length < 3) {
              const src = $(this).attr('src');
              if (src) {
                referenceImages.push(src);
              }
            }
          });
        }
      });

      console.log('Quickbrush | Opening dialog for type:', type);
      console.log('Quickbrush | Text length:', textContent.length);
      console.log('Quickbrush | Reference images:', referenceImages.length);

      new QuickbrushDialog({
        data: {
          text: textContent,
          generation_type: type,
          aspect_ratio: type === 'scene' ? 'landscape' : 'square',
          referenceImages
        }
      }).render(true);
    });

    $menu.append(menuItem);
  });
});

/**
 * Add Quickbrush button to Journal Directory
 * This adds a button in the journal tab (like lava-flow does)
 */
Hooks.on('renderJournalDirectory', (app, html) => {
  if (!game.user.isGM) return;

  console.log('Quickbrush | Adding UI button to journal directory');

  // In V13, html might be an HTMLElement, not jQuery, so wrap it
  const $html = html instanceof jQuery ? html : $(html);

  const buttons = $(`
    <button class="quickbrush-sync-btn">
      <i class="fas fa-sync"></i> Quickbrush Sync
    </button>
    <button class="quickbrush-directory-btn">
      <i class="fas fa-palette"></i> ${game.i18n.localize('QUICKBRUSH.ButtonLabel')}
    </button>
  `);

  buttons.filter('.quickbrush-directory-btn').on('click', function() {
    console.log('Quickbrush | Opening generation dialog from directory button');
    new QuickbrushDialog().render(true);
  });

  buttons.filter('.quickbrush-sync-btn').on('click', async function() {
    await QuickbrushGallery.syncFromLibrary();
  });

  $html.find('.directory-header .header-actions').append(buttons);
});

/**
 * Strip HTML tags and clean text
 */
function stripHTML(html) {
  if (!html) return '';

  // Create a temporary div to parse HTML
  const temp = document.createElement('div');
  temp.innerHTML = html;

  // Get text content
  const text = temp.textContent || temp.innerText || '';

  // Clean up whitespace
  return text.replace(/\s+/g, ' ').trim();
}

/**
 * Resolve Foundry @Embed tags and enrich text
 */
async function enrichAndStripText(text) {
  if (!text) return '';

  try {
    // Use Foundry's TextEditor to enrich the text (resolves @Embed, @UUID, etc.)
    const enriched = await TextEditor.enrichHTML(text, {
      async: true,
      secrets: false,
      documents: true,
      links: true,
      rolls: false,
      rollData: {}
    });

    // Strip HTML tags from the enriched content
    return stripHTML(enriched);
  } catch (err) {
    console.warn('Quickbrush | Failed to enrich text, using fallback:', err);
    // Fallback: just strip @Embed tags manually and clean HTML
    const withoutEmbeds = text.replace(/@Embed\[[^\]]+\]/g, '');
    return stripHTML(withoutEmbeds);
  }
}

/**
 * Extract rich text description from actor with metadata
 */
async function extractActorText(actor, actorType) {
  let parts = [];

  // Add name
  parts.push(`Name: ${actor.name}`);

  if (actorType === 'character') {
    // Character-specific metadata
    if (actor.system.details?.race?.name) {
      parts.push(`Race: ${actor.system.details.race.name}`);
    }

    // Class and level
    const classes = [];
    if (actor.items) {
      actor.items.forEach(item => {
        if (item.type === 'class') {
          const level = item.system.levels || 1;
          classes.push(`${item.name} ${level}`);
        }
      });
    }
    if (classes.length > 0) {
      parts.push(`Class: ${classes.join(', ')}`);
    }

    // Background
    if (actor.system.details?.background?.name) {
      parts.push(`Background: ${actor.system.details.background.name}`);
    }

    // Alignment
    if (actor.system.details?.alignment) {
      parts.push(`Alignment: ${actor.system.details.alignment}`);
    }

  } else {
    // NPC/Creature metadata
    if (actor.system.details?.type?.value) {
      parts.push(`Type: ${actor.system.details.type.value}`);
    }

    // Size
    if (actor.system.traits?.size) {
      parts.push(`Size: ${actor.system.traits.size}`);
    }

    // CR
    if (actor.system.details?.cr !== undefined) {
      parts.push(`CR: ${actor.system.details.cr}`);
    }

    // Alignment
    if (actor.system.details?.alignment) {
      parts.push(`Alignment: ${actor.system.details.alignment}`);
    }
  }

  // Add biography/description
  let description = '';
  if (actor.system.details?.biography?.value) {
    description = actor.system.details.biography.value;
  } else if (actor.system.biography?.value) {
    description = actor.system.biography.value;
  } else if (actor.system.description?.value) {
    description = actor.system.description.value;
  }

  if (description) {
    // Enrich and strip HTML tags from description
    const stripped = await enrichAndStripText(description);
    if (stripped) {
      parts.push(`\nDescription: ${stripped}`);
    }
  }

  return parts.join('\n');
}

/**
 * Extract rich text description from item with metadata
 */
async function extractItemText(item) {
  let parts = [];

  // Add name
  parts.push(`Name: ${item.name}`);

  // Item type
  if (item.type) {
    parts.push(`Type: ${item.type.charAt(0).toUpperCase() + item.type.slice(1)}`);
  }

  // Rarity
  if (item.system.rarity) {
    parts.push(`Rarity: ${item.system.rarity.charAt(0).toUpperCase() + item.system.rarity.slice(1)}`);
  }

  // Value
  if (item.system.price?.value) {
    const currency = item.system.price.denomination || 'gp';
    parts.push(`Value: ${item.system.price.value} ${currency}`);
  }

  // Weight
  if (item.system.weight?.value) {
    parts.push(`Weight: ${item.system.weight.value} lbs`);
  }

  // Properties (for weapons/armor)
  if (item.system.properties) {
    const props = [];
    for (const [key, enabled] of Object.entries(item.system.properties)) {
      if (enabled) props.push(key);
    }
    if (props.length > 0) {
      parts.push(`Properties: ${props.join(', ')}`);
    }
  }

  // Damage (for weapons)
  if (item.system.damage?.parts && item.system.damage.parts.length > 0) {
    const damageStr = item.system.damage.parts.map(p => `${p[0]} ${p[1]}`).join(', ');
    parts.push(`Damage: ${damageStr}`);
  }

  // AC (for armor)
  if (item.system.armor?.value) {
    parts.push(`AC: ${item.system.armor.value}`);
  }

  // Description
  let description = '';
  if (item.system.description?.value) {
    description = item.system.description.value;
  } else if (item.system.details?.description?.value) {
    description = item.system.details.description.value;
  }

  if (description) {
    // Enrich and strip HTML tags from description
    const stripped = await enrichAndStripText(description);
    if (stripped) {
      parts.push(`\nDescription: ${stripped}`);
    }
  }

  return parts.join('\n');
}

/**
 * Helper function to add Quickbrush to actor sheet
 */
function addQuickbrushToActorSheet(app, html, actorType) {
  console.log(`Quickbrush | Rendering ${actorType} actor sheet`);
  if (!game.user.isGM) return;

  const $html = html instanceof jQuery ? html : $(html);

  // Try both selectors
  let $menu = $html.find('menu.controls-dropdown');
  if ($menu.length === 0) {
    $menu = $html.find('menu.context-menu');
  }

  console.log('Quickbrush | Menu found:', $menu.length > 0, 'HTML classes:', $menu.attr('class'));

  if ($menu.length === 0) return;

  // Get the actor document
  const actor = app.document || app.actor || app.object;
  if (!actor) {
    console.warn('Quickbrush | Could not find actor document');
    return;
  }

  // Check if already added to prevent duplicates
  if ($menu.find('[data-action="quickbrush-actor"]').length > 0) {
    console.log('Quickbrush | Already added, skipping');
    return;
  }

  const isCharacter = actorType === 'character';
  const generationType = isCharacter ? 'character' : 'creature';
  const label = isCharacter ? '🎭 Character' : '🐉 Creature';
  const icon = isCharacter ? 'fa-user' : 'fa-dragon';

  const menuItem = $(`
    <li class="header-control" data-action="quickbrush-actor">
      <button type="button" class="control">
        <i class="control-icon fa-fw fa-solid ${icon}"></i>
        <span class="control-label">Quickbrush: ${label}</span>
      </button>
    </li>
  `);

  menuItem.find('button').on('click', () => {
    console.log('Quickbrush | Generate button clicked for actor:', actor.name);

    // Extract actor description/biography
    let textContent = actor.name;

    // Try to get biography/description from system data
    if (actor.system.details?.biography?.value) {
      textContent = actor.system.details.biography.value;
    } else if (actor.system.biography?.value) {
      textContent = actor.system.biography.value;
    } else if (actor.system.description?.value) {
      textContent = actor.system.description.value;
    }

    // Extract images from actor's img property
    const referenceImages = [];
    if (actor.img && !actor.img.includes('mystery-man')) {
      referenceImages.push(actor.img);
    }

    console.log('Quickbrush | Opening dialog for actor:', actor.name);
    console.log('Quickbrush | Text length:', textContent.length);
    console.log('Quickbrush | Reference images:', referenceImages.length);

    new QuickbrushDialog({
      targetDocument: actor,
      data: {
        text: textContent,
        generation_type: generationType,
        aspect_ratio: 'square',
        referenceImages
      }
    }).render(true);
  });

  $menu.append(menuItem);
  console.log('Quickbrush | Menu item appended to', $menu.attr('class'));

  // Listen for the toggle button click to add to the dynamically created context menu
  const $toggleButton = $html.find('button[data-action="toggleControls"]');
  if ($toggleButton.length > 0) {
    console.log('Quickbrush | Found toggle button, adding click listener');

    $toggleButton.on('click', () => {
      console.log('Quickbrush | Toggle button clicked');

      // Wait for the context menu to be created
      setTimeout(() => {
        const $contextMenu = $('#context-menu');
        console.log('Quickbrush | Context menu found:', $contextMenu.length > 0);

        if ($contextMenu.length > 0) {
          const $contextItems = $contextMenu.find('menu.context-items');
          console.log('Quickbrush | Context items container found:', $contextItems.length > 0);

          // Check if already added
          if ($contextItems.find('.quickbrush-context-item').length === 0) {
            console.log('Quickbrush | Adding to context menu');

            const contextItem = $(`
              <li class="context-item quickbrush-context-item">
                <i class="fa-solid ${icon} fa-fw" inert=""></i>
                <span>Quickbrush: ${label}</span>
              </li>
            `);

            contextItem.on('click', async () => {
              console.log('Quickbrush | Context menu item clicked');
              // Close the context menu
              $contextMenu[0]?.hidePopover?.();

              // Extract rich text content with metadata
              const textContent = await extractActorText(actor, actorType);

              // Extract images from actor's img property
              const referenceImages = [];
              if (actor.img && !actor.img.includes('mystery-man')) {
                referenceImages.push(actor.img);
              }

              console.log('Quickbrush | Opening dialog for actor:', actor.name);
              console.log('Quickbrush | Extracted text:', textContent.substring(0, 200) + '...');

              new QuickbrushDialog({
                targetDocument: actor,
                data: {
                  text: textContent,
                  generation_type: generationType,
                  aspect_ratio: 'square',
                  referenceImages
                }
              }).render(true);
            });

            $contextItems.append(contextItem);
            console.log('Quickbrush | Added to context menu');

            // Force the context menu to recalculate its height
            const contextMenuElement = $contextMenu[0];
            if (contextMenuElement) {
              // Remove any max-height constraints that might have been set
              $contextMenu.css('max-height', 'none');
              $contextItems.css('max-height', 'none');

              // Force a reflow
              contextMenuElement.style.height = 'auto';

              console.log('Quickbrush | Context menu height adjusted');
            }
          } else {
            console.log('Quickbrush | Already in context menu');
          }
        }
      }, 50);
    });
  }
}

/**
 * Add Quickbrush options to Character Actor sheet controls dropdown
 */
Hooks.on('renderCharacterActorSheet', (app, html) => {
  addQuickbrushToActorSheet(app, html, 'character');
});

/**
 * Add Quickbrush options to NPC Actor sheet controls dropdown
 */
Hooks.on('renderNPCActorSheet', (app, html) => {
  addQuickbrushToActorSheet(app, html, 'npc');
});

/**
 * Add Quickbrush options to Item sheet controls dropdown
 */
Hooks.on('renderItemSheet5e', (app, html) => {
  console.log('Quickbrush | Rendering item sheet');
  if (!game.user.isGM) return;

  const $html = html instanceof jQuery ? html : $(html);

  const item = app.document || app.item || app.object;
  if (!item) {
    console.warn('Quickbrush | Could not find item document');
    return;
  }

  // Listen for the toggle button click to add to the dynamically created context menu
  const $toggleButton = $html.find('button[data-action="toggleControls"]');
  if ($toggleButton.length > 0) {
    console.log('Quickbrush | Found item toggle button, adding click listener');

    $toggleButton.on('click', () => {
      console.log('Quickbrush | Item toggle button clicked');

      // Wait for the context menu to be created
      setTimeout(() => {
        const $contextMenu = $('#context-menu');
        console.log('Quickbrush | Item context menu found:', $contextMenu.length > 0);

        if ($contextMenu.length > 0) {
          const $contextItems = $contextMenu.find('menu.context-items');

          // Check if already added
          if ($contextItems.find('.quickbrush-context-item').length === 0) {
            console.log('Quickbrush | Adding to item context menu');

            const contextItem = $(`
              <li class="context-item quickbrush-context-item">
                <i class="fa-solid fa-gem fa-fw" inert=""></i>
                <span>Quickbrush: 🗡️ Item</span>
              </li>
            `);

            contextItem.on('click', async () => {
              console.log('Quickbrush | Item context menu item clicked');
              // Close the context menu
              $contextMenu[0]?.hidePopover?.();

              // Extract rich text content with metadata
              const textContent = await extractItemText(item);

              // Extract images from item's img property
              const referenceImages = [];
              if (item.img && !item.img.includes('mystery-man')) {
                referenceImages.push(item.img);
              }

              console.log('Quickbrush | Opening dialog for item:', item.name);
              console.log('Quickbrush | Extracted text:', textContent.substring(0, 200) + '...');

              new QuickbrushDialog({
                targetDocument: item,
                data: {
                  text: textContent,
                  generation_type: 'item',
                  aspect_ratio: 'square',
                  referenceImages
                }
              }).render(true);
            });

            $contextItems.append(contextItem);
            console.log('Quickbrush | Added to item context menu');

            // Force the context menu to recalculate its height
            const contextMenuElement = $contextMenu[0];
            if (contextMenuElement) {
              // Remove any max-height constraints that might have been set
              $contextMenu.css('max-height', 'none');
              $contextItems.css('max-height', 'none');

              // Force a reflow
              contextMenuElement.style.height = 'auto';

              console.log('Quickbrush | Item context menu height adjusted');
            }
          } else {
            console.log('Quickbrush | Already in item context menu');
          }
        }
      }, 50);
    });
  }
});

// Export for console access
window.Quickbrush = {
  API: QuickbrushAPI,
  Dialog: QuickbrushDialog,
  Gallery: QuickbrushGallery
};
