# Quickbrush Static Site

This directory contains the static website for Quickbrush, hosted on GitHub Pages.

## Features

- **Home Page**: Introduction to Quickbrush and the BYOK model
- **Showcase**: Visual examples of the FoundryVTT module in action
- **Generate**: Client-side image generation using your OpenAI API key
- **Library**: Browser-based image library using IndexedDB
- **AI & Artists**: Our commitment to ethical AI use

## Technology

- Pure HTML/CSS/JavaScript (no build process required)
- Bootstrap 5.3.3 for styling
- IndexedDB for local image storage
- localStorage for API key storage
- quickbrush-core.js for image generation logic

## Local Development

Simply open any HTML file in a web browser. For the generate page to work properly, you'll need to serve it over HTTP (not file://):

```bash
# Using Python
python -m http.server 8000

# Using Node.js
npx serve

# Then visit http://localhost:8000
```

## Deployment

The site is automatically deployed to GitHub Pages when changes are pushed to the `docs/` directory on the main branch.

## Privacy

All user data (API keys, generated images) is stored locally in the browser. Nothing is sent to our servers.
