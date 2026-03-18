#!/usr/bin/env node
/**
 * Click an element.
 * Usage: node click.js --selector ".button" [--wait-for ".result"] [--timeout 5000]
 */
import { getBrowser, getPage, disconnectBrowser, parseArgs, outputJSON, outputError } from './lib/browser.js';
import { parseSelector, waitForElement, clickElement, enhanceError } from './lib/selector.js';

async function click() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.selector) { outputError(new Error('--selector is required')); return; }

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

    const navigationPromise = page.waitForNavigation({
      waitUntil: 'load', timeout: 5000
    }).catch(() => null);

    await clickElement(page, parsed);

    if (args['wait-for']) {
      await page.waitForSelector(args['wait-for'], {
        timeout: parseInt(args.timeout || '5000')
      });
    } else {
      await navigationPromise;
    }

    outputJSON({
      success: true,
      url: page.url(),
      title: await page.title()
    });
    await disconnectBrowser();
  } catch (error) {
    await disconnectBrowser();
    outputError(enhanceError(error, args.selector));
  }
}

click();
