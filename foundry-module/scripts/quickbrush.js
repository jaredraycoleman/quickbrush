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
  async generateImage({ text, prompt = '', generation_type = 'character', quality = 'medium', aspect_ratio = 'square' }) {
    if (!this.apiKey) {
      throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.NoApiKey'));
    }

    const response = await fetch(`${this.apiUrl}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: JSON.stringify({
        text,
        prompt,
        generation_type,
        quality,
        aspect_ratio
      })
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));

      // Handle specific error types
      if (response.status === 429) {
        throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.RateLimit'));
      } else if (response.status === 402) {
        throw new Error(game.i18n.localize('QUICKBRUSH.Notifications.InsufficientBrushstrokes'));
      }

      throw new Error(error.detail || error.message || 'Unknown error');
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
      // Show progress notification
      ui.notifications.info(game.i18n.localize('QUICKBRUSH.Notifications.Generating'));

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

      // Success!
      ui.notifications.info(game.i18n.format('QUICKBRUSH.Notifications.Saved', {
        folder: folder
      }));

      this.close();

    } catch (error) {
      console.error('Quickbrush generation error:', error);
      ui.notifications.error(game.i18n.format('QUICKBRUSH.Notifications.Error', {
        error: error.message
      }));
    }
  }
}

/**
 * Gallery Manager
 */
class QuickbrushGallery {
  static GALLERY_NAME = 'Quickbrush Gallery';

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
        name: this.GALLERY_NAME,
        content: `<h1>${game.i18n.localize('QUICKBRUSH.Gallery.Title')}</h1><p>${game.i18n.localize('QUICKBRUSH.Gallery.Description')}</p><hr>`
      });
    }

    return journal;
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

    console.log(journal);

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

  console.log('Quickbrush | Extracted text length:', textContent.length);
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
});

Hooks.once('ready', () => {
  console.log('Quickbrush | Module ready');
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
      console.log('Quickbrush | Opening dialog for type:', type, 'with text:', textContent.substring(0, 100));
      new QuickbrushDialog({
        data: {
          text: textContent,
          generation_type: type,
          aspect_ratio: type === 'scene' ? 'landscape' : 'square'
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
    <button class="quickbrush-directory-btn">
      <i class="fas fa-palette"></i> ${game.i18n.localize('QUICKBRUSH.ButtonLabel')}
    </button>
    <button class="quickbrush-sync-btn">
      <i class="fas fa-sync"></i> Sync Quickbrush Library
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

// Export for console access
window.Quickbrush = {
  API: QuickbrushAPI,
  Dialog: QuickbrushDialog,
  Gallery: QuickbrushGallery
};
