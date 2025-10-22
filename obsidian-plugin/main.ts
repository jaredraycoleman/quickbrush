import { App, Plugin, PluginSettingTab, Setting, Notice, TFile, TFolder, Modal, TextAreaComponent, TextComponent, DropdownComponent, requestUrl } from 'obsidian';

interface QuickBrushSettings {
	apiKey: string;
	apiUrl: string;
	quickbrushFolder: string;
}

const DEFAULT_SETTINGS: QuickBrushSettings = {
	apiKey: '',
	apiUrl: 'https://quickbrush.online/api',
	quickbrushFolder: 'Quickbrush'
};

interface GenerationOptions {
	text: string;
	image_name: string;
	prompt?: string;
	generation_type: 'character' | 'scene' | 'creature' | 'item';
	quality: 'low' | 'medium' | 'high';
	aspect_ratio: 'square' | 'landscape' | 'portrait';
	reference_image_paths?: string[];
}

interface GenerationResponse {
	success: boolean;
	generation_id: string;
	image_url: string;
	refined_description: string;
	image_name?: string;
	brushstrokes_used: number;
	brushstrokes_remaining: number;
	remaining_image_slots: number;
	message: string;
}

interface UserInfo {
	email: string;
	brushstrokes: number;
	generations_used: number;
	max_generations: number;
}

export default class QuickBrushPlugin extends Plugin {
	settings: QuickBrushSettings;

	// Helper methods to get derived folder paths
	getImagesFolder(): string {
		return `${this.settings.quickbrushFolder}/quickbrush-images`;
	}

	getGalleryFolder(): string {
		return `${this.settings.quickbrushFolder}/quickbrush-gallery`;
	}

	getGenerationsBasePath(): string {
		return `${this.settings.quickbrushFolder}/quickbrush-generations.base`;
	}

	async onload() {
		await this.loadSettings();

		// Add ribbon icon
		this.addRibbonIcon('image-plus', 'QuickBrush', () => {
			this.openGenerateModal();
		});

		// Add commands for each generation type
		this.addCommand({
			id: 'generate-character',
			name: 'Generate Character Image',
			callback: () => {
				this.openGenerateModal('character');
			}
		});

		this.addCommand({
			id: 'generate-scene',
			name: 'Generate Scene Image',
			callback: () => {
				this.openGenerateModal('scene');
			}
		});

		this.addCommand({
			id: 'generate-creature',
			name: 'Generate Creature Image',
			callback: () => {
				this.openGenerateModal('creature');
			}
		});

		this.addCommand({
			id: 'generate-item',
			name: 'Generate Item Image',
			callback: () => {
				this.openGenerateModal('item');
			}
		});

		// Add settings tab
		this.addSettingTab(new QuickBrushSettingTab(this.app, this));
	}

	async loadSettings() {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
	}

	async saveSettings() {
		await this.saveData(this.settings);
	}

	openGenerateModal(defaultType?: 'character' | 'scene' | 'creature' | 'item') {
		if (!this.settings.apiKey) {
			new Notice('API Key Required: Please set your QuickBrush API key in the plugin settings. Get your key from quickbrush.online.', 6000);
			return;
		}

		const activeFile = this.app.workspace.getActiveFile();
		let initialText = '';
		let initialImages: string[] = [];
		let initialName = '';

		if (activeFile) {
			// Get the note title (filename without extension)
			initialName = activeFile.basename;

			this.app.vault.read(activeFile).then(async content => {
				// Extract content without frontmatter
				initialText = this.extractContentWithoutFrontmatter(content);

				// Extract first 3 images from the note
				const imagePaths = this.extractImagePaths(content);

				// Convert images to base64
				for (const imagePath of imagePaths) {
					const base64 = await this.resolveImageToBase64(imagePath);
					if (base64) {
						initialImages.push(base64);
					}
				}

				new GenerateModal(this.app, this, initialText, initialImages, initialName, defaultType).open();
			});
		} else {
			new GenerateModal(this.app, this, initialText, initialImages, initialName, defaultType).open();
		}
	}

	extractContentWithoutFrontmatter(content: string): string {
		// Remove YAML frontmatter
		const frontmatterRegex = /^---\n[\s\S]*?\n---\n/;
		let text = content.replace(frontmatterRegex, '');

		// Remove markdown formatting for cleaner text
		text = text
			.replace(/!\[\[.*?\]\]/g, '') // Remove image embeds
			.replace(/\[\[(.*?)\]\]/g, '$1') // Convert wiki links to text
			.replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1') // Convert markdown links to text
			.replace(/^#{1,6}\s+/gm, '') // Remove headers
			.replace(/\*\*/g, '') // Remove bold
			.replace(/\*/g, '') // Remove italic
			.replace(/^[-*+]\s+/gm, '') // Remove list markers
			.trim();

		// Limit to 10000 characters
		if (text.length > 10000) {
			text = text.substring(0, 10000);
		}

		return text;
	}

	extractImagePaths(content: string): string[] {
		const images: string[] = [];

		// Extract wiki-link image embeds: ![[image.png]]
		const wikiImageRegex = /!\[\[([^\]]+\.(png|jpg|jpeg|gif|webp|bmp))\]\]/gi;
		let match;
		while ((match = wikiImageRegex.exec(content)) !== null && images.length < 3) {
			images.push(match[1]);
		}

		// If we need more, extract markdown image embeds: ![alt](image.png)
		if (images.length < 3) {
			const mdImageRegex = /!\[[^\]]*\]\(([^\)]+\.(png|jpg|jpeg|gif|webp|bmp))\)/gi;
			while ((match = mdImageRegex.exec(content)) !== null && images.length < 3) {
				images.push(match[1]);
			}
		}

		return images;
	}

	async resolveImageToBase64(imagePath: string): Promise<string | null> {
		try {
			// Try to find the file in the vault
			const file = this.app.metadataCache.getFirstLinkpathDest(imagePath, '');
			if (!file || !(file instanceof TFile)) {
				return null;
			}

			// Read the file as binary
			const arrayBuffer = await this.app.vault.readBinary(file);

			// Convert to base64
			const base64 = this.arrayBufferToBase64(arrayBuffer);

			// Determine mime type from extension
			const ext = file.extension.toLowerCase();
			const mimeTypes: { [key: string]: string } = {
				'png': 'image/png',
				'jpg': 'image/jpeg',
				'jpeg': 'image/jpeg',
				'gif': 'image/gif',
				'webp': 'image/webp',
				'bmp': 'image/bmp'
			};
			const mimeType = mimeTypes[ext] || 'image/png';

			return `data:${mimeType};base64,${base64}`;
		} catch (error) {
			console.error(`Failed to resolve image ${imagePath}:`, error);
			return null;
		}
	}

	arrayBufferToBase64(buffer: ArrayBuffer): string {
		let binary = '';
		const bytes = new Uint8Array(buffer);
		const len = bytes.byteLength;
		for (let i = 0; i < len; i++) {
			binary += String.fromCharCode(bytes[i]);
		}
		return window.btoa(binary);
	}

	async ensureFolderExists(folderPath: string): Promise<void> {
		const folder = this.app.vault.getAbstractFileByPath(folderPath);
		if (!folder) {
			await this.app.vault.createFolder(folderPath);
		}
	}

	async generateImage(options: GenerationOptions): Promise<GenerationResponse> {
		const url = `${this.settings.apiUrl}/generate`;

		try {
			const response = await requestUrl({
				url,
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${this.settings.apiKey}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(options),
				throw: false // Don't throw on non-2xx status codes
			});

			// Success case
			if (response.status === 200) {
				return response.json;
			}

			// Error cases - extract the error message from the API response
			let apiErrorMessage = 'Unknown error';
			try {
				const errorData = response.json;
				apiErrorMessage = errorData.detail || errorData.message || apiErrorMessage;
			} catch (e) {
				// Ignore JSON parse errors
			}

			// Handle specific status codes with helpful messages
			if (response.status === 401) {
				throw new Error(`Invalid API Key: ${apiErrorMessage}\n\nPlease check your QuickBrush settings and update your API key from quickbrush.online.`);
			} else if (response.status === 402) {
				throw new Error(`Insufficient Brushstrokes: ${apiErrorMessage}\n\nVisit quickbrush.online to purchase more or upgrade your subscription.`);
			} else if (response.status === 429) {
				throw new Error(`Rate Limit Exceeded: ${apiErrorMessage}\n\nPlease wait before trying again. Limits: 1 per 10 seconds, 50 per hour.`);
			} else if (response.status === 422) {
				// Validation error - try to extract field-specific details
				let errorDetails = apiErrorMessage;
				try {
					const errorData = response.json;
					if (errorData.detail && Array.isArray(errorData.detail)) {
						errorDetails = errorData.detail.map((e: any) => {
							const field = e.loc ? e.loc.join('.') : 'field';
							const msg = e.msg || e.message || 'validation error';
							return `${field}: ${msg}`;
						}).join('\n');
					}
				} catch (e) {
					// Use apiErrorMessage as fallback
				}
				throw new Error(`Validation Error: ${errorDetails}\n\nPlease check your inputs and try again.`);
			} else {
				throw new Error(`Generation Failed (${response.status}): ${apiErrorMessage}\n\nIf this persists, please contact support at quickbrush.online.`);
			}
		} catch (error) {
			// If it's already a formatted error from above, re-throw it
			if (error instanceof Error && error.message.includes(':')) {
				throw error;
			}

			// Network or unexpected errors
			console.error('QuickBrush API error:', error);
			throw new Error('Network Error: Failed to connect to QuickBrush API. Please check your internet connection and API URL in settings.');
		}
	}

	async downloadImage(generationId: string): Promise<ArrayBuffer> {
		const url = `${this.settings.apiUrl}/image/${generationId}`;

		try {
			const response = await requestUrl({
				url,
				method: 'GET',
				headers: {
					'Authorization': `Bearer ${this.settings.apiKey}`
				},
				throw: false // Don't throw on non-2xx status codes
			});

			// Success case
			if (response.status === 200) {
				return response.arrayBuffer;
			}

			// Error cases - extract error message from API
			let apiErrorMessage = 'Unknown error';
			try {
				const errorData = response.json;
				apiErrorMessage = errorData.detail || errorData.message || apiErrorMessage;
			} catch (e) {
				// Ignore JSON parse errors
			}

			// Handle specific status codes
			if (response.status === 404) {
				throw new Error(`Image Not Found: ${apiErrorMessage}\n\nThe generated image could not be found. It may have been deleted or exceeded the storage limit.`);
			} else if (response.status === 401) {
				throw new Error(`Invalid API Key: ${apiErrorMessage}\n\nUnable to download image. Please check your API key in settings.`);
			} else {
				throw new Error(`Download Failed (${response.status}): ${apiErrorMessage}\n\nPlease try again.`);
			}
		} catch (error) {
			// If it's already a formatted error from above, re-throw it
			if (error instanceof Error && error.message.includes(':')) {
				throw error;
			}

			// Network or unexpected errors
			console.error('QuickBrush download error:', error);
			throw new Error('Network Error: Failed to download image from QuickBrush. Please check your internet connection.');
		}
	}

	async saveImageToVault(generationId: string, imageData: ArrayBuffer, imageName?: string): Promise<string> {
		const imagesFolder = this.getImagesFolder();
		await this.ensureFolderExists(imagesFolder);

		// Use image name if available, otherwise use generation ID
		let filename: string;
		if (imageName) {
			// Sanitize the image name for use as filename
			const sanitized = imageName.replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');
			filename = `${sanitized}.webp`;
		} else {
			filename = `quickbrush-${generationId}.webp`;
		}

		const filepath = `${imagesFolder}/${filename}`;

		await this.app.vault.createBinary(filepath, imageData);

		return filepath;
	}

	async createGalleryNote(
		filepath: string,
		generationType: string,
		description: string,
		refinedDescription: string,
		prompt: string,
		quality: string,
		aspectRatio: string,
		brushstrokesUsed: number,
		imageName?: string
	): Promise<void> {
		const galleryFolder = this.getGalleryFolder();
		await this.ensureFolderExists(galleryFolder);

		// Ensure the generations base file exists
		await this.ensureGenerationsBaseExists();

		// Create timestamp
		const now = new Date();
		const timestamp = this.formatTimestamp(now);

		// Create filename with image name if available
		let noteFilename: string;
		if (imageName) {
			// Sanitize the image name for use as filename
			const sanitized = imageName.replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');
			noteFilename = `${sanitized} - ${timestamp}.md`;
		} else {
			noteFilename = `${timestamp}.md`;
		}

		const notePath = `${galleryFolder}/${noteFilename}`;

		// Create frontmatter properties
		const properties = {
			date: now.toISOString(),
			generation_type: generationType,
			quality: quality,
			aspect_ratio: aspectRatio,
			brushstrokes_used: brushstrokesUsed,
			image: `[[${filepath}]]`,
		};

		// Build note content
		let content = '---\n';
		for (const [key, value] of Object.entries(properties)) {
			// Escape quotes in string values
			const escapedValue = typeof value === 'string' ? value.replace(/"/g, '\\"') : value;
			content += `${key}: "${escapedValue}"\n`;
		}
		content += '---\n\n';
		content += `![[${filepath}]]\n`;

		// add original description, refined description, and prompt below the image
		content += `\n**Original Description:**\n\n${description}\n`;
		content += `\n**Refined Description:**\n\n${refinedDescription}\n`;
		if (prompt) {
			content += `\n**Context Prompt:**\n\n${prompt}\n`;
		}

		await this.app.vault.create(notePath, content);
	}

	async ensureGenerationsBaseExists(): Promise<void> {
		const basePath = this.getGenerationsBasePath();
		const baseFile = this.app.vault.getAbstractFileByPath(basePath);

		if (!baseFile) {
			// Create the parent folder if needed
			await this.ensureFolderExists(this.settings.quickbrushFolder);

			// Create the .base file with Dataview query content
			const galleryFolder = this.getGalleryFolder();
			const content = `
filters:
  and:
    - file.folder == "${galleryFolder}"
formulas:
  image: image(image)
properties:
  note.date:
    displayName: Date
  note.generation_type:
    displayName: Type
  note.quality:
    displayName: Quality
  note.aspect_ratio:
    displayName: AR
  note.brushstrokes_used:
    displayName: Brushstrokes
views:
  - type: table
    name: Table
    order:
      - file.name
      - formula.image
      - aspect_ratio
      - brushstrokes_used
      - date
      - generation_type
      - quality
    sort:
      - property: date
        direction: DESC
    rowHeight: tall
    columnSize:
      file.name: 343
      formula.image: 201
`;
			await this.app.vault.create(basePath, content);
		}
	}

	formatTimestamp(date: Date): string {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		const hours = String(date.getHours()).padStart(2, '0');
		const minutes = String(date.getMinutes()).padStart(2, '0');
		const seconds = String(date.getSeconds()).padStart(2, '0');

		return `${year}-${month}-${day} ${hours}${minutes}${seconds}`;
	}

	async getUserInfo(): Promise<UserInfo> {
		const url = `${this.settings.apiUrl}/user`;

		const response = await requestUrl({
			url,
			method: 'GET',
			headers: {
				'Authorization': `Bearer ${this.settings.apiKey}`
			}
		});

		return response.json;
	}
}

class GenerateModal extends Modal {
	plugin: QuickBrushPlugin;
	initialText: string;
	initialImages: string[];
	initialName: string;
	defaultType?: string;

	textInput: TextAreaComponent;
	nameInput: TextComponent;
	promptInput: TextAreaComponent;
	typeDropdown: DropdownComponent;
	qualityDropdown: DropdownComponent;
	aspectRatioDropdown: DropdownComponent;
	referenceImages: string[];

	constructor(app: App, plugin: QuickBrushPlugin, initialText: string, initialImages: string[], initialName: string, defaultType?: string) {
		super(app);
		this.plugin = plugin;
		this.initialText = initialText;
		this.initialImages = initialImages;
		this.initialName = initialName;
		this.defaultType = defaultType;
		this.referenceImages = [...initialImages];
	}

	onOpen() {
		const { contentEl } = this;
		contentEl.empty();

		contentEl.createEl('h2', { text: 'Generate QuickBrush Image' });

		// Generation Type
		new Setting(contentEl)
			.setName('Generation Type')
			.setDesc('Select the type of image to generate')
			.addDropdown(dropdown => {
				this.typeDropdown = dropdown;
				dropdown
					.addOption('character', 'Character')
					.addOption('scene', 'Scene')
					.addOption('creature', 'Creature')
					.addOption('item', 'Item')
					.setValue(this.defaultType || 'character')
					.onChange(() => {
						// Auto-set aspect ratio based on type
						const type = this.typeDropdown.getValue();
						if (type === 'scene') {
							this.aspectRatioDropdown.setValue('landscape');
						} else {
							this.aspectRatioDropdown.setValue('square');
						}
					});
			});

		// Description
		new Setting(contentEl)
			.setName('Description')
			.setDesc('Describe what you want to generate (max 10,000 characters)')
			.addTextArea(text => {
				this.textInput = text;
				text
					.setPlaceholder('Enter a description...')
					.setValue(this.initialText)
					.inputEl.rows = 8;
				text.inputEl.style.width = '100%';
			});

		// Image Name
		new Setting(contentEl)
			.setName('Image Name')
			.setDesc('This will be used as the filename when saving your image')
			.addText(text => {
				this.nameInput = text;
				text
					.setPlaceholder('e.g., Elven Warrior, Ancient Library')
					.setValue(this.initialName);
				text.inputEl.style.width = '100%';
			});

		// Context Prompt
		new Setting(contentEl)
			.setName('Context Prompt (Optional)')
			.setDesc('Specific instructions on what to paint (max 1000 characters)')
			.addTextArea(text => {
				this.promptInput = text;
				text
					.setPlaceholder('e.g., "In golden light, heroic pose"')
					.inputEl.rows = 3;
				text.inputEl.style.width = '100%';
			});

		// Reference Images
		const refImagesSetting = new Setting(contentEl)
			.setName('Reference Images (Optional)')
			.setDesc(`${this.referenceImages.length} of 3 images selected`)
			.addButton(button => button
				.setButtonText('Add Image')
				.setDisabled(this.referenceImages.length >= 3)
				.onClick(async () => {
					await this.selectReferenceImage(updateRefImagesDisplay);
				}));

		const refImagesContainer = contentEl.createDiv({ cls: 'quickbrush-ref-images' });
		refImagesContainer.style.display = 'flex';
		refImagesContainer.style.flexWrap = 'wrap';
		refImagesContainer.style.gap = '10px';
		refImagesContainer.style.marginBottom = '20px';

		const updateRefImagesDisplay = () => {
			refImagesContainer.empty();
			refImagesSetting.setDesc(`${this.referenceImages.length} of 3 images selected`);

			// Update button state
			const addButton = refImagesSetting.controlEl.querySelector('button');
			if (addButton) {
				(addButton as HTMLButtonElement).disabled = this.referenceImages.length >= 3;
			}

			this.referenceImages.forEach((imgData, index) => {
				const imgWrapper = refImagesContainer.createDiv({ cls: 'ref-image-wrapper' });
				imgWrapper.style.position = 'relative';
				imgWrapper.style.width = '80px';
				imgWrapper.style.height = '80px';

				const img = imgWrapper.createEl('img');
				img.src = imgData;
				img.style.width = '100%';
				img.style.height = '100%';
				img.style.objectFit = 'cover';
				img.style.borderRadius = '4px';

				const removeBtn = imgWrapper.createEl('button', { cls: 'ref-image-remove' });
				removeBtn.textContent = '×';
				removeBtn.style.position = 'absolute';
				removeBtn.style.top = '2px';
				removeBtn.style.right = '2px';
				removeBtn.style.width = '20px';
				removeBtn.style.height = '20px';
				removeBtn.style.borderRadius = '50%';
				removeBtn.style.background = 'var(--background-modifier-error)';
				removeBtn.style.color = 'white';
				removeBtn.style.border = 'none';
				removeBtn.style.cursor = 'pointer';
				removeBtn.style.fontSize = '14px';
				removeBtn.style.lineHeight = '1';

				removeBtn.addEventListener('click', () => {
					this.referenceImages.splice(index, 1);
					updateRefImagesDisplay();
				});
			});

			if (this.referenceImages.length === 0) {
				const note = refImagesContainer.createDiv();
				note.style.fontSize = '0.9em';
				note.style.color = 'var(--text-muted)';
				note.textContent = 'No reference images selected';
			} else if (this.initialImages.length > 0 && this.referenceImages.length === this.initialImages.length) {
				const note = refImagesContainer.createDiv();
				note.style.fontSize = '0.9em';
				note.style.color = 'var(--text-muted)';
				note.textContent = `${this.initialImages.length} image(s) auto-selected from note`;
			}
		};

		updateRefImagesDisplay();

		// Quality
		new Setting(contentEl)
			.setName('Quality')
			.setDesc('Higher quality uses more brushstrokes')
			.addDropdown(dropdown => {
				this.qualityDropdown = dropdown;
				dropdown
					.addOption('low', 'Low (1 brushstroke)')
					.addOption('medium', 'Medium (3 brushstrokes)')
					.addOption('high', 'High (5 brushstrokes)')
					.setValue('medium');
			});

		// Aspect Ratio
		new Setting(contentEl)
			.setName('Aspect Ratio')
			.addDropdown(dropdown => {
				this.aspectRatioDropdown = dropdown;
				dropdown
					.addOption('square', 'Square (1024x1024)')
					.addOption('landscape', 'Landscape (1536x1024)')
					.addOption('portrait', 'Portrait (1024x1536)')
					.setValue(this.defaultType === 'scene' ? 'landscape' : 'square');
			});

		// Buttons
		const buttonContainer = contentEl.createDiv({ cls: 'quickbrush-button-container' });
		buttonContainer.style.display = 'flex';
		buttonContainer.style.justifyContent = 'flex-end';
		buttonContainer.style.gap = '10px';
		buttonContainer.style.marginTop = '20px';

		const cancelButton = buttonContainer.createEl('button', { text: 'Cancel' });
		cancelButton.addEventListener('click', () => {
			this.close();
		});

		const generateButton = buttonContainer.createEl('button', {
			text: 'Generate',
			cls: 'mod-cta'
		});
		generateButton.addEventListener('click', () => {
			this.handleGenerate();
		});
	}

	async selectReferenceImage(updateDisplay: () => void) {
		if (this.referenceImages.length >= 3) {
			new Notice('Maximum Reference Images: You can only select up to 3 reference images.', 4000);
			return;
		}

		// Create a file input element
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = 'image/*';
		input.multiple = false;

		input.onchange = async (e) => {
			const file = (e.target as HTMLInputElement).files?.[0];
			if (!file) return;

			// Check if it's an image
			if (!file.type.startsWith('image/')) {
				new Notice('Invalid File Type: Please select an image file (PNG, JPG, GIF, WebP, etc.).', 5000);
				return;
			}

			// Check file size (warn if > 10MB)
			const maxSize = 10 * 1024 * 1024; // 10MB
			if (file.size > maxSize) {
				new Notice('Large File Warning: This image is quite large and may slow down generation. Consider using a smaller image.', 6000);
			}

			try {
				// Read the file as base64
				const reader = new FileReader();
				reader.onload = (event) => {
					const base64 = event.target?.result as string;
					this.referenceImages.push(base64);
					updateDisplay();
					new Notice('Reference image added successfully', 3000);
				};
				reader.onerror = () => {
					new Notice('File Read Error: Unable to read the selected image file. Please try a different file.', 5000);
				};
				reader.readAsDataURL(file);
			} catch (error) {
				new Notice('Error Loading Image: An unexpected error occurred while loading the image. Please try again.', 5000);
				console.error('QuickBrush image load error:', error);
			}
		};

		input.click();
	}

	async handleGenerate() {
		const text = this.textInput.getValue().trim();
		if (!text) {
			new Notice('Description Required: Please enter a description of what you want to generate.', 5000);
			return;
		}

		const imageName = this.nameInput.getValue().trim();
		if (!imageName) {
			new Notice('Image Name Required: Please enter a name for your image.', 5000);
			return;
		}

		const options: GenerationOptions = {
			text: text.substring(0, 10000),
			image_name: imageName,
			prompt: this.promptInput.getValue().substring(0, 1000) || undefined,
			generation_type: this.typeDropdown.getValue() as any,
			quality: this.qualityDropdown.getValue() as any,
			aspect_ratio: this.aspectRatioDropdown.getValue() as any,
			reference_image_paths: this.referenceImages.length > 0 ? this.referenceImages : undefined
		};

		this.close();

		const notice = new Notice('Generating image...', 0);

		try {
			// Generate image
			const result = await this.plugin.generateImage(options);
			notice.setMessage('Downloading image...');

			// Download image
			const imageData = await this.plugin.downloadImage(result.generation_id);
			notice.setMessage('Saving image...');

			// Save to vault with image name
			const filepath = await this.plugin.saveImageToVault(result.generation_id, imageData, result.image_name);

			// Create gallery note with image name
			await this.plugin.createGalleryNote(
				filepath,
				options.generation_type,
				options.text,
				result.refined_description,
				options.prompt || '',
				options.quality,
				options.aspect_ratio,
				result.brushstrokes_used,
				result.image_name
			);

			notice.hide();
			new Notice(`Image generated successfully! ${result.brushstrokes_remaining} brushstrokes remaining.`);

		} catch (error) {
			notice.hide();
			if (error instanceof Error) {
				// Show detailed error message
				new Notice(error.message, 8000); // Show for 8 seconds

				// Log full error for debugging
				console.error('QuickBrush generation error:', error);
			} else {
				new Notice('Unexpected Error: Failed to generate image. Please try again or contact support.', 6000);
				console.error('QuickBrush unknown error:', error);
			}
		}
	}

	onClose() {
		const { contentEl } = this;
		contentEl.empty();
	}
}

class QuickBrushSettingTab extends PluginSettingTab {
	plugin: QuickBrushPlugin;

	constructor(app: App, plugin: QuickBrushPlugin) {
		super(app, plugin);
		this.plugin = plugin;
	}

	display(): void {
		const { containerEl } = this;
		containerEl.empty();

		containerEl.createEl('h2', { text: 'QuickBrush Settings' });

		// API Key
		new Setting(containerEl)
			.setName('API Key')
			.setDesc('Your QuickBrush API key from quickbrush.online')
			.addText(text => text
				.setPlaceholder('Enter your API key')
				.setValue(this.plugin.settings.apiKey)
				.onChange(async (value) => {
					this.plugin.settings.apiKey = value;
					await this.plugin.saveSettings();
				}));

		// API URL
		new Setting(containerEl)
			.setName('API URL')
			.setDesc('QuickBrush API endpoint (change only if using a custom server)')
			.addText(text => text
				.setPlaceholder('https://quickbrush.online/api')
				.setValue(this.plugin.settings.apiUrl)
				.onChange(async (value) => {
					this.plugin.settings.apiUrl = value;
					await this.plugin.saveSettings();
				}));

		// QuickBrush Folder
		new Setting(containerEl)
			.setName('QuickBrush Folder')
			.setDesc('Parent folder for all QuickBrush files (images, gallery, and index)')
			.addText(text => text
				.setPlaceholder('Quickbrush')
				.setValue(this.plugin.settings.quickbrushFolder)
				.onChange(async (value) => {
					this.plugin.settings.quickbrushFolder = value;
					await this.plugin.saveSettings();
				}));

		// Info about derived folders
		const folderInfo = containerEl.createDiv();
		folderInfo.style.fontSize = '0.9em';
		folderInfo.style.color = 'var(--text-muted)';
		folderInfo.style.marginTop = '-10px';
		folderInfo.style.marginBottom = '20px';
		folderInfo.innerHTML = `
			<p>Images will be saved to: <code>${this.plugin.getImagesFolder()}</code></p>
			<p>Gallery notes will be saved to: <code>${this.plugin.getGalleryFolder()}</code></p>
			<p>Gallery index will be created at: <code>${this.plugin.getGenerationsBasePath()}</code></p>
		`;

		// Account Info Section
		containerEl.createEl('h3', { text: 'Account Information' });

		const accountInfoContainer = containerEl.createDiv();
		const refreshButton = new Setting(accountInfoContainer)
			.setName('Account Status')
			.setDesc('Loading...')
			.addButton(button => button
				.setButtonText('Refresh')
				.onClick(async () => {
					await this.loadAccountInfo(accountInfoContainer, refreshButton);
				}));

		this.loadAccountInfo(accountInfoContainer, refreshButton);

		// Help Section
		containerEl.createEl('h3', { text: 'Help' });
		const helpText = containerEl.createDiv();
		helpText.innerHTML = `
			<p>Get your API key from <a href="https://quickbrush.online">quickbrush.online</a></p>
			<p>Use the ribbon icon or command palette to generate images.</p>
			<p>Generated images are saved to the Images Folder and gallery notes are created in the Gallery Folder.</p>
		`;
	}

	async loadAccountInfo(container: HTMLElement, setting: Setting) {
		if (!this.plugin.settings.apiKey) {
			setting.setDesc('Please set your API key above');
			return;
		}

		try {
			const userInfo = await this.plugin.getUserInfo();
			setting.setDesc(
				`Email: ${userInfo.email}\n` +
				`Brushstrokes: ${userInfo.brushstrokes}\n` +
				`Generations: ${userInfo.generations_used} / ${userInfo.max_generations}`
			);
		} catch (error) {
			setting.setDesc('Failed to load account info. Please check your API key.');
		}
	}
}
