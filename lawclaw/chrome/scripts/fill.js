#!/usr/bin/env node
/**
 * Fill form fields.
 * Usage: node fill.js --selector "#input" --value "text" [--clear true] [--delay 50]
 */
import { getBrowser, getPage, disconnectBrowser, parseArgs, outputJSON, outputError } from './lib/browser.js';
import { parseSelector, waitForElement, typeIntoElement, enhanceError } from './lib/selector.js';

async function fill() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.selector) { outputError(new Error('--selector is required')); return; }
  if (!args.value) { outputError(new Error('--value is required')); return; }

  try {
    const browser = await getBrowser();
    const page = await getPage(browser);

    if (args.url) {
      await page.goto(args.url, { waitUntil: args['wait-until'] || 'networkidle2' });
    }

    const parsed = parseSelector(args.selector);
    await waitForElement(page, parsed, {
      visible: true,
      timeout: parseInt(args.timeout || '5000')
    });

    await typeIntoElement(page, parsed, args.value, {
      clear: args.clear === 'true',
      delay: parseInt(args.delay || '0')
    });

    outputJSON({
      success: true,
      selector: args.selector,
      value: args.value,
      url: page.url()
    });
    await disconnectBrowser();
  } catch (error) {
    await disconnectBrowser();
    outputError(enhanceError(error, args.selector));
  }
}

fill();
