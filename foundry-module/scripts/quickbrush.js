/**
 * Quickbrush Image Generator for Foundry VTT
 * Generate fantasy RPG artwork using your own OpenAI API key
 */

const MODULE_ID = 'quickbrush';

/**
 * Load QuickbrushCore library dynamically
 * The core library is bundled from packages/quickbrush-core
 */
let QuickbrushCore = null;

async function loadQuickbrushCore() {
  if (QuickbrushCore) {
    return QuickbrushCore; // Already loaded
  }

  // Load the bundled core library
  const coreUrl = 'modules/quickbrush/scripts/quickbrush-core.js';
  const absoluteUrl = new URL(coreUrl, window.location.origin).href;

  console.log(`Quickbrush | Loading core library from: ${absoluteUrl}`);

  try {
    const module = await import(absoluteUrl);
    QuickbrushCore = module.QuickbrushCore || module;
    console.log('Quickbrush | Core library loaded successfully');
    return QuickbrushCore;
  } catch (error) {
    console.error('Quickbrush | Failed to load core library', error);
    ui.notifications.error('Quickbrush: Failed to load core library. Please check your module installation.');
    throw error;
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
      image_name: this.data.image_name || this.targetDocument?.name || '',
      prompt: this.data.prompt || '',
      generation_type: this.data.generation_type || 'character',
      quality: this.data.quality || 'high',
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
        if (this.referenceImages.length < 4) {
          this.referenceImages.push(path);
          this.render();
        } else {
          ui.notifications.warn('Maximum 4 reference images allowed', { permanent: false });
        }
      }
    });
    fp.browse();
  }

  /**
   * Convert image paths to base64 data URIs
   * This ensures images can be sent to OpenAI API
   */
  async convertImagesToBase64(imagePaths) {
    const base64Images = [];

    for (const imagePath of imagePaths) {
      try {
        // Fetch the image
        const response = await fetch(imagePath);
        if (!response.ok) {
          console.warn(`Failed to fetch reference image: ${imagePath}`);
          continue;
        }

        // Get the blob
        const blob = await response.blob();

        // Convert to base64
        const base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });

        base64Images.push(base64);
      } catch (error) {
        console.warn(`Error converting image to base64: ${imagePath}`, error);
      }
    }

    return base64Images;
  }

  async _updateObject(event, formData) {
    event.preventDefault();

    // Validate
    if (!formData.text || !formData.text.trim()) {
      ui.notifications.warn('Please provide a description for your image.');
      return;
    }

    if (!formData.image_name || !formData.image_name.trim()) {
      ui.notifications.warn('Please provide a name for your image.');
      return;
    }

    // Check for OpenAI API key
    const openaiApiKey = game.settings.get(MODULE_ID, 'openaiApiKey');
    if (!openaiApiKey) {
      ui.notifications.error('Please configure your OpenAI API key in module settings first.');
      return;
    }

    try {
      // Close the dialog immediately so user can continue working
      this.close();

      // Show single notification that generation has started
      ui.notifications.info('Generating image... This may take 30-60 seconds. You\'ll be notified when it\'s ready!', { permanent: false });

      // Load the core library dynamically
      const core = await loadQuickbrushCore();

      // Convert reference images to base64 data URIs
      const referenceImagePaths = this.referenceImages || [];
      const base64ReferenceImages = referenceImagePaths.length > 0
        ? await this.convertImagesToBase64(referenceImagePaths)
        : [];

      // Create OpenAI client and generator
      const client = new core.OpenAIClient(openaiApiKey);
      const generator = core.createGenerator(formData.generation_type, client);

      // Get selected model from settings
      const imageModel = game.settings.get(MODULE_ID, 'imageModel') || 'gpt-image-1-mini';

      // Step 1: Extract/refine description
      ui.notifications.info('Step 1/2: Refining description...', { permanent: false });
      const description = await generator.getDescription(
        formData.text,
        formData.prompt || null,
        base64ReferenceImages
      );

      console.log('Quickbrush | Refined description:', description.text);

      // Step 2: Generate image
      ui.notifications.info('Step 2/2: Generating image...', { permanent: false });
      const imageBlob = await generator.generateImage({
        description: description.text,
        referenceImages: base64ReferenceImages,
        model: imageModel,
        quality: formData.quality,
        aspectRatio: formData.aspect_ratio
      });

      // Save to Foundry
      const folder = await QuickbrushGallery.getOrCreateFolder();

      // Use image name if available
      const sanitized = formData.image_name.replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');
      const filename = `${sanitized}-${Date.now()}.png`;

      const file = new File([imageBlob], filename, { type: 'image/png' });

      const uploadResult = await FilePicker.upload('data', folder, file);

      // Update gallery
      await QuickbrushGallery.addToGallery({
        imageUrl: uploadResult.path,
        type: formData.generation_type,
        description: formData.text,
        prompt: formData.prompt,
        quality: formData.quality,
        aspectRatio: formData.aspect_ratio,
        refinedDescription: description.text,
        imageName: formData.image_name
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
          I'm <strong>Wispy Quickbrush</strong>, halfling artist extraordinaire and your magical companion in creating breathtaking artwork for your campaigns! With a flick of my enchanted brush and the power of AI, I can bring your characters, creatures, items, and scenes to life faster than a wizard can say "prestidigitation!"
        </p>
        <p>
          Whether you need a portrait of a noble paladin, a fearsome dragon, or a mysterious magical artifact, I'm here to help paint your imagination onto the canvas of reality. Well... digital reality, at least! 🖌️✨
        </p>

        <h2>📖 How to Use Quickbrush</h2>

        <h3>🔑 First Things First: Setting Up Your OpenAI API Key</h3>
        <p>Quickbrush now uses a <strong>Bring Your Own Key</strong> model - you'll use your own OpenAI API key:</p>
        <ol>
          <li>Visit <a href="https://platform.openai.com/api-keys" target="_blank">OpenAI Platform</a> and create an account</li>
          <li>Generate an API key from your account dashboard</li>
          <li>Add credits to your OpenAI account at <a href="https://platform.openai.com/account/billing" target="_blank">OpenAI Billing</a></li>
          <li>In Foundry VTT, go to <strong>Settings</strong> → <strong>Configure Settings</strong> → <strong>Module Settings</strong></li>
          <li>Find <strong>Quickbrush</strong> and configure:
            <ul>
              <li>Paste your OpenAI API key in the <strong>OpenAI API Key</strong> field</li>
              <li>Choose your preferred <strong>Image Model</strong> (GPT-Image-1-Mini is default, faster and cheaper)</li>
            </ul>
          </li>
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
          <li><strong>Description:</strong> Long-form text describing the subject (e.g., journal entry, character background). May include irrelevant details — I'll focus on the physical description!</li>
          <li><strong>Context Prompt (Optional):</strong> Specific instructions about what to focus on (e.g., "wearing a red cloak", "in a defensive stance", "at sunset"). <em>This takes priority over the description!</em></li>
          <li><strong>Quality:</strong>
            <ul>
              <li><strong>Low (Standard):</strong> Fast generation, lower cost</li>
              <li><strong>Medium (Standard):</strong> Balanced quality and cost</li>
              <li><strong>High (HD):</strong> Best quality, higher cost</li>
            </ul>
          </li>
          <li><strong>Aspect Ratio:</strong> Square (1024x1024), Landscape (1536x1024), or Portrait (1024x1536)</li>
          <li><strong>Reference Images:</strong> Upload up to 4 reference images to guide the composition, style, and visual elements. Both GPT-Image-1 and GPT-Image-1-Mini support reference images to help create art that matches your vision!</li>
          <li><strong>Auto-Update:</strong> When generating from a character/item sheet, check this to automatically set the image</li>
        </ul>

        <h3>📸 Your Gallery</h3>
        <p>All your generated images are automatically saved to this journal's <strong>Images</strong> page! You can browse your artistic collection, copy images to use elsewhere, or just admire my handiwork. 😊</p>

        <h2>⚠️ Important Information</h2>

        <h3>🤖 AI-Powered Art</h3>
        <p>Quickbrush uses OpenAI's GPT-Image models (GPT-Image-1 or GPT-Image-1-Mini) to generate images based on your descriptions. While I do my best to create exactly what you envision, AI-generated art can sometimes be... creative! You might occasionally get unexpected results, unusual anatomy, or mysterious extra fingers. That's just part of the magical chaos! 🎲</p>

        <p><strong>Please note:</strong> Generated images are subject to OpenAI's content policies. Keep your prompts family-friendly and in line with the heroic spirit of adventure!</p>

        <h3>💰 Pricing & Costs</h3>
        <p>Since you're using your own OpenAI API key, you'll be billed directly by OpenAI based on their pricing:</p>
        <p>Check your usage at <a href="https://platform.openai.com/usage" target="_blank">OpenAI Platform Usage</a>!</p>

        <hr style="margin: 2em 0;">

        <p style="text-align: center; font-style: italic;">
          <strong>Happy adventuring, and may your campaigns be filled with beautiful art!</strong>
        </p>
        <p style="text-align: center;">
          — Wispy Quickbrush 🎨✨
        </p>
        <p style="text-align: center; font-size: 0.9em; margin-top: 1.5em;">
          Quickbrush Module v2.0.0
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
  static async addToGallery({ imageUrl, type, description, prompt, quality, aspectRatio, refinedDescription, imageName }) {
    const journal = await this.getOrCreateGalleryJournal();
    const date = new Date().toLocaleString();

    // Create a title with image name if available
    let title = imageName ? `${imageName} - ${date}` : date;

    const template = game.i18n.localize('QUICKBRUSH.Gallery.EntryTemplate');
    const entry = template
      .replace('{type}', type.charAt(0).toUpperCase() + type.slice(1))
      .replace('{date}', title)
      .replace('{description}', description)
      .replace('{quality}', quality.charAt(0).toUpperCase() + quality.slice(1))
      .replace('{aspectRatio}', aspectRatio)
      .replace('{imageUrl}', imageUrl);

    // Get the "Images" page specifically (not the About page)
    let page = journal.pages.find(p => p.name === 'Images');

    if (!page) {
      // Create the Images page
      const pages = await journal.createEmbeddedDocuments('JournalEntryPage', [{
        name: 'Images',
        type: 'text',
        text: { content: '', format: CONST.JOURNAL_ENTRY_PAGE_FORMATS.HTML },
        sort: 1 // Sort after the About page
      }]);
      page = pages[0];
    }

    // Prepend new entry to existing content
    const currentContent = page.text.content || '';
    await page.update({
      'text.content': entry + currentContent
    });

    // Don't show notification here - let the caller show a single comprehensive notification
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

    // Limit to maximum allowed length (10000 characters)
    textContent = textContent.substring(0, 10000).trim();
  }

  return textContent;
}

/**
 * Module Initialization
 */
Hooks.once('init', () => {
  console.log('Quickbrush | Initializing module');

  // Register settings
  game.settings.register(MODULE_ID, 'openaiApiKey', {
    name: game.i18n.localize('QUICKBRUSH.Settings.OpenAIApiKey.Name'),
    hint: game.i18n.localize('QUICKBRUSH.Settings.OpenAIApiKey.Hint'),
    scope: 'world',
    config: true,
    type: String,
    default: ''
  });

  game.settings.register(MODULE_ID, 'imageModel', {
    name: game.i18n.localize('QUICKBRUSH.Settings.ImageModel.Name'),
    hint: game.i18n.localize('QUICKBRUSH.Settings.ImageModel.Hint'),
    scope: 'world',
    config: true,
    type: String,
    choices: {
      'gpt-image-1-mini': game.i18n.localize('QUICKBRUSH.Settings.ImageModel.Choices.mini'),
      'gpt-image-1': game.i18n.localize('QUICKBRUSH.Settings.ImageModel.Choices.standard')
    },
    default: 'gpt-image-1-mini'
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

  // Check if already added to prevent duplicates
  if ($menu.find('[data-action^="quickbrush-"]').length > 0) {
    console.log('Quickbrush | Already added to journal menu, skipping');
    return;
  }

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

      // Extract first 4 images from journal
      const referenceImages = [];
      const $visiblePages = $html.find('article.journal-entry-page');
      $visiblePages.each(function() {
        if (referenceImages.length < 4) {
          $(this).find('.journal-page-content img').each(function() {
            if (referenceImages.length < 4) {
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
        },
        targetDocument: app.document
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

  const button = $(`
    <button class="quickbrush-directory-btn">
      <i class="fas fa-palette"></i> ${game.i18n.localize('QUICKBRUSH.ButtonLabel')}
    </button>
  `);

  button.on('click', function() {
    console.log('Quickbrush | Opening generation dialog from directory button');
    new QuickbrushDialog().render(true);
  });

  $html.find('.directory-header .header-actions').append(button);
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

  // Determine generation type based on creature type
  let generationType = isCharacter ? 'character' : 'creature';

  // For NPCs, check if they're humanoid
  if (actorType === 'npc') {
    const creatureType = actor.system.details?.type?.value || '';
    const isHumanoid = creatureType.toLowerCase().includes('humanoid');
    generationType = isHumanoid ? 'character' : 'creature';
  }

  const label = generationType === 'character' ? '🎭 Character' : '🐉 Creature';
  const icon = generationType === 'character' ? 'fa-user' : 'fa-dragon';

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
  Dialog: QuickbrushDialog,
  Gallery: QuickbrushGallery
};
