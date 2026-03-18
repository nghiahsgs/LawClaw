#!/usr/bin/env node
/**
 * Take a screenshot.
 * Usage: node screenshot.js --output screenshot.png [--full-page true] [--selector .element]
 */
import { getBrowser, getPage, disconnectBrowser, parseArgs, outputJSON, outputError } from './lib/browser.js';
import { parseSelector, getElement, enhanceError } from './lib/selector.js';
import path from 'path';

async function screenshot() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.output) { outputError(new Error('--output is required')); return; }

  try {
    const browser = await getBrowser();
    const page = await getPage(browser);

    if (args.url) {
      await page.goto(args.url, { waitUntil: args['wait-until'] || 'networkidle2' });
    }

    const screenshotOptions = {
      path: args.output,
      type: args.format || 'png',
      fullPage: args['full-page'] === 'true'
    };
    if (args.quality) screenshotOptions.quality = parseInt(args.quality);

    let buffer;
    if (args.selector) {
      const parsed = parseSelector(args.selector);
      const element = await getElement(page, parsed);
      if (!element) throw new Error(`Element not found: ${args.selector}`);
      buffer = await element.screenshot(screenshotOptions);
    } else {
      buffer = await page.screenshot(screenshotOptions);
    }

    outputJSON({
      success: true,
      output: path.resolve(args.output),
      size: buffer.length,
      url: page.url()
    });
    await disconnectBrowser();
  } catch (error) {
    await disconnectBrowser();
    if (args.selector) outputError(enhanceError(error, args.selector));
    else outputError(error);
  }
}

screenshot();
