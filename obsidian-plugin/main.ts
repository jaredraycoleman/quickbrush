import { App, Plugin, PluginSettingTab, Setting, Notice, TFile, TFolder, Modal, TextAreaComponent, DropdownComponent, requestUrl } from 'obsidian';

interface QuickBrushSettings {
	apiKey: string;
	apiUrl: string;
	imagesFolder: string;
	galleryFolder: string;
}

const DEFAULT_SETTINGS: QuickBrushSettings = {
	apiKey: '',
	apiUrl: 'https://quickbrush.online/api',
	imagesFolder: 'quickbrush-images',
	galleryFolder: 'quickbrush-gallery'
};

interface GenerationOptions {
	text: string;
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
			new Notice('Please set your QuickBrush API key in settings');
			return;
		}

		const activeFile = this.app.workspace.getActiveFile();
		let initialText = '';

		if (activeFile) {
			this.app.vault.read(activeFile).then(content => {
				// Extract content without frontmatter
				initialText = this.extractContentWithoutFrontmatter(content);
				new GenerateModal(this.app, this, initialText, defaultType).open();
			});
		} else {
			new GenerateModal(this.app, this, initialText, defaultType).open();
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

		// Limit to 4000 characters
		if (text.length > 4000) {
			text = text.substring(0, 4000);
		}

		return text;
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
				body: JSON.stringify(options)
			});

			if (response.status === 200) {
				return response.json;
			} else if (response.status === 401) {
				throw new Error('Invalid API key. Please check your settings.');
			} else if (response.status === 402) {
				throw new Error('Insufficient brushstrokes. Please visit quickbrush.online to get more.');
			} else if (response.status === 429) {
				throw new Error('Rate limit exceeded. Please wait before generating another image.');
			} else {
				throw new Error(`Generation failed: ${response.json.message || 'Unknown error'}`);
			}
		} catch (error) {
			if (error instanceof Error) {
				throw error;
			}
			throw new Error('Failed to connect to QuickBrush API');
		}
	}

	async downloadImage(generationId: string): Promise<ArrayBuffer> {
		const url = `${this.settings.apiUrl}/image/${generationId}`;

		const response = await requestUrl({
			url,
			method: 'GET',
			headers: {
				'Authorization': `Bearer ${this.settings.apiKey}`
			}
		});

		return response.arrayBuffer;
	}

	async saveImageToVault(generationId: string, imageData: ArrayBuffer): Promise<string> {
		await this.ensureFolderExists(this.settings.imagesFolder);

		const filename = `quickbrush-${generationId}.webp`;
		const filepath = `${this.settings.imagesFolder}/${filename}`;

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
		brushstrokesUsed: number
	): Promise<void> {
		await this.ensureFolderExists(this.settings.galleryFolder);

		// Create timestamp-based filename
		const now = new Date();
		const timestamp = this.formatTimestamp(now);
		const noteFilename = `${timestamp}.md`;
		const notePath = `${this.settings.galleryFolder}/${noteFilename}`;

		// Create frontmatter properties
		const properties = {
			date: now.toISOString(),
			generation_type: generationType,
			quality: quality,
			aspect_ratio: aspectRatio,
			brushstrokes_used: brushstrokesUsed
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
			content += `\n**Artistic Prompt:**\n\n${prompt}\n`;
		}

		await this.app.vault.create(notePath, content);
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
	defaultType?: string;

	textInput: TextAreaComponent;
	promptInput: TextAreaComponent;
	typeDropdown: DropdownComponent;
	qualityDropdown: DropdownComponent;
	aspectRatioDropdown: DropdownComponent;

	constructor(app: App, plugin: QuickBrushPlugin, initialText: string, defaultType?: string) {
		super(app);
		this.plugin = plugin;
		this.initialText = initialText;
		this.defaultType = defaultType;
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

		// Artistic Prompt
		new Setting(contentEl)
			.setName('Artistic Prompt (Optional)')
			.setDesc('Additional styling or mood guidance (max 500 characters)')
			.addTextArea(text => {
				this.promptInput = text;
				text
					.setPlaceholder('e.g., "In golden light, heroic pose"')
					.inputEl.rows = 3;
				text.inputEl.style.width = '100%';
			});

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

	async handleGenerate() {
		const text = this.textInput.getValue().trim();
		if (!text) {
			new Notice('Please enter a description');
			return;
		}

		const options: GenerationOptions = {
			text: text.substring(0, 10000),
			prompt: this.promptInput.getValue().substring(0, 500) || undefined,
			generation_type: this.typeDropdown.getValue() as any,
			quality: this.qualityDropdown.getValue() as any,
			aspect_ratio: this.aspectRatioDropdown.getValue() as any
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

			// Save to vault
			const filepath = await this.plugin.saveImageToVault(result.generation_id, imageData);

			// Create gallery note
			await this.plugin.createGalleryNote(
				filepath,
				options.generation_type,
				options.text,
				result.refined_description,
				options.prompt || '',
				options.quality,
				options.aspect_ratio,
				result.brushstrokes_used
			);

			notice.hide();
			new Notice(`Image generated successfully! ${result.brushstrokes_remaining} brushstrokes remaining.`);

		} catch (error) {
			notice.hide();
			if (error instanceof Error) {
				new Notice(`Error: ${error.message}`);
			} else {
				new Notice('Failed to generate image');
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

		// Images Folder
		new Setting(containerEl)
			.setName('Images Folder')
			.setDesc('Folder to save generated images')
			.addText(text => text
				.setPlaceholder('quickbrush-images')
				.setValue(this.plugin.settings.imagesFolder)
				.onChange(async (value) => {
					this.plugin.settings.imagesFolder = value;
					await this.plugin.saveSettings();
				}));

		// Gallery Folder
		new Setting(containerEl)
			.setName('Gallery Folder')
			.setDesc('Folder to save gallery notes with image metadata')
			.addText(text => text
				.setPlaceholder('quickbrush-gallery')
				.setValue(this.plugin.settings.galleryFolder)
				.onChange(async (value) => {
					this.plugin.settings.galleryFolder = value;
					await this.plugin.saveSettings();
				}));

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
