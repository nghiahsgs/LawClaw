#!/usr/bin/env node
/**
 * Navigate to a URL.
 * Usage: node navigate.js --url https://example.com [--wait-until networkidle2] [--timeout 30000]
 */
import { getBrowser, getPage, disconnectBrowser, parseArgs, outputJSON, outputError } from './lib/browser.js';

async function navigate() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) { outputError(new Error('--url is required')); return; }

  try {
    const browser = await getBrowser();
    const page = await getPage(browser);

    await page.goto(args.url, {
      waitUntil: args['wait-until'] || 'networkidle2',
      timeout: parseInt(args.timeout || '30000')
    });

    outputJSON({
      success: true,
      url: page.url(),
      title: await page.title()
    });
    await disconnectBrowser();
  } catch (error) {
    await disconnectBrowser();
    outputError(error);
  }
}

navigate();
