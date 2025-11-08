#!/usr/bin/env node

/**
 * Script to publish a Foundry VTT package using the Package Release API
 * Documentation: https://foundryvtt.com/article/package-release-api/
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// Load environment variables from .env file
function loadEnv() {
  const envPath = path.join(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) {
    console.error('Error: .env file not found');
    process.exit(1);
  }

  const envContent = fs.readFileSync(envPath, 'utf8');
  envContent.split('\n').forEach(line => {
    const match = line.match(/^([^=]+)=(.*)$/);
    if (match) {
      const key = match[1].trim();
      let value = match[2].trim();
      // Remove quotes if present
      value = value.replace(/^["']|["']$/g, '');
      process.env[key] = value;
    }
  });
}

// Load module.json
function loadModuleJson() {
  const modulePath = path.join(__dirname, '..', 'foundry-module', 'module.json');
  if (!fs.existsSync(modulePath)) {
    console.error('Error: module.json not found at', modulePath);
    process.exit(1);
  }

  const moduleContent = fs.readFileSync(modulePath, 'utf8');
  return JSON.parse(moduleContent);
}

// Make API request to Foundry
function publishToFoundry(apiKey, packageData, dryRun = false) {
  const requestBody = JSON.stringify({
    id: packageData.id,
    'dry-run': dryRun,
    release: {
      version: packageData.version,
      manifest: packageData.manifest,
      notes: `https://github.com/wizzlethorpe/quickbrush/releases/tag/v${packageData.version}`,
      compatibility: packageData.compatibility
    }
  });

  const options = {
    hostname: 'foundryvtt.com',
    path: '/_api/packages/release_version/',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': apiKey,
      'Content-Length': Buffer.byteLength(requestBody)
    }
  };

  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          resolve({ statusCode: res.statusCode, data: response });
        } catch (error) {
          resolve({ statusCode: res.statusCode, data: data });
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.write(requestBody);
    req.end();
  });
}

// Main execution
async function main() {
  // Parse command line arguments
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');

  console.log('Loading environment variables...');
  loadEnv();

  const apiKey = process.env.FOUNDRY_RELEASE_API_KEY;
  if (!apiKey) {
    console.error('Error: FOUNDRY_RELEASE_API_KEY not found in .env file');
    process.exit(1);
  }

  console.log('Loading module.json...');
  const moduleData = loadModuleJson();

  console.log('\n=== Package Release Information ===');
  console.log(`Package ID: ${moduleData.id}`);
  console.log(`Version: ${moduleData.version}`);
  console.log(`Manifest URL: ${moduleData.manifest}`);
  console.log(`Compatibility: minimum ${moduleData.compatibility.minimum}, verified ${moduleData.compatibility.verified}`);
  console.log(`Mode: ${dryRun ? 'DRY RUN (no changes will be saved)' : 'LIVE RELEASE'}`);
  console.log('===================================\n');

  try {
    console.log('Publishing to Foundry VTT...');
    const result = await publishToFoundry(apiKey, moduleData, dryRun);

    console.log(`\nResponse Status: ${result.statusCode}`);
    console.log('Response Data:', JSON.stringify(result.data, null, 2));

    if (result.statusCode === 200) {
      console.log('\n✅ Success!');
      if (dryRun) {
        console.log('Dry run completed. To publish for real, run without --dry-run flag.');
      } else {
        console.log('Package published successfully!');
        if (result.data.page) {
          console.log(`View at: ${result.data.page}`);
        }
      }
    } else {
      console.error('\n❌ Error: Release failed');
      process.exit(1);
    }
  } catch (error) {
    console.error('\n❌ Error:', error.message);
    process.exit(1);
  }
}

main();
