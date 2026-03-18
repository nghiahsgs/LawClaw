#!/usr/bin/env node
/**
 * Execute JavaScript in page context.
 * Usage: node evaluate.js --script "document.title" [--url https://example.com]
 */
import { getBrowser, getPage, disconnectBrowser, parseArgs, outputJSON, outputError } from './lib/browser.js';

async function evaluate() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.script) { outputError(new Error('--script is required')); return; }

  try {
    const browser = await getBrowser();
    const page = await getPage(browser);

    if (args.url) {
      await page.goto(args.url, { waitUntil: args['wait-until'] || 'networkidle2' });
    }

    const result = await page.evaluate((script) => {
      return eval(script);
    }, args.script);

    outputJSON({
      success: true,
      result: result,
      url: page.url()
    });
    await disconnectBrowser();
  } catch (error) {
    await disconnectBrowser();
    outputError(error);
  }
}

evaluate();
