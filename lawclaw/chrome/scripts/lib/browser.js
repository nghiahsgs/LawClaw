/**
 * Shared browser utilities for LawClaw Chrome scripts.
 * State files (.browser-endpoint, .profile-meta) stored at ~/.lawclaw/workspace/chrome/
 * Profiles stored at ~/.lawclaw/workspace/chrome/profiles/{name}/
 */
import puppeteer from 'puppeteer';
import debug from 'debug';
import fs from 'fs';
import path from 'path';
import os from 'os';

const CHROME_DIR = path.join(os.homedir(), '.lawclaw', 'workspace', 'chrome');
const ENDPOINT_FILE = path.join(CHROME_DIR, '.browser-endpoint');

const log = debug('lawclaw:chrome');

let browserInstance = null;
let pageInstance = null;

/**
 * Launch or connect to browser
 */
export async function getBrowser(options = {}) {
  if (browserInstance && browserInstance.isConnected()) {
    log('Reusing existing browser instance');
    return browserInstance;
  }

  // Check for persistent browser endpoint
  if (!options.browserUrl && !options.wsEndpoint && fs.existsSync(ENDPOINT_FILE)) {
    try {
      const wsEndpoint = fs.readFileSync(ENDPOINT_FILE, 'utf8').trim();
      log('Found persistent browser endpoint, connecting...');
      browserInstance = await puppeteer.connect({ browserWSEndpoint: wsEndpoint });
      return browserInstance;
    } catch (error) {
      log('Failed to connect to persistent browser:', error.message);
      if (fs.existsSync(ENDPOINT_FILE)) {
        fs.unlinkSync(ENDPOINT_FILE);
      }
    }
  }

  const launchOptions = {
    headless: options.headless !== false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      ...(options.args || [])
    ],
    defaultViewport: options.viewport || { width: 1920, height: 1080 },
    ...options
  };

  if (options.browserUrl || options.wsEndpoint) {
    log('Connecting to existing browser');
    browserInstance = await puppeteer.connect({
      browserURL: options.browserUrl,
      browserWSEndpoint: options.wsEndpoint
    });
  } else {
    log('Launching new browser');
    browserInstance = await puppeteer.launch(launchOptions);
  }

  return browserInstance;
}

/**
 * Get current page or create new one
 */
export async function getPage(browser) {
  if (pageInstance && !pageInstance.isClosed()) {
    log('Reusing existing page');
    return pageInstance;
  }

  const pages = await browser.pages();
  pageInstance = pages.length > 0 ? pages[0] : await browser.newPage();
  return pageInstance;
}

/**
 * Disconnect from browser (keeps browser alive, releases WebSocket)
 */
export async function disconnectBrowser() {
  if (browserInstance) {
    browserInstance.disconnect();
    browserInstance = null;
    pageInstance = null;
  }
}

/**
 * Close browser entirely
 */
export async function closeBrowser() {
  if (browserInstance) {
    await browserInstance.close();
    browserInstance = null;
    pageInstance = null;
  }
}

/**
 * Parse command line arguments
 */
export function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const nextArg = argv[i + 1];
      if (nextArg && !nextArg.startsWith('--')) {
        args[key] = nextArg;
        i++;
      } else {
        args[key] = true;
      }
    }
  }
  return args;
}

export function outputJSON(data) {
  console.log(JSON.stringify(data));
}

export function outputError(error) {
  console.error(JSON.stringify({
    success: false,
    error: error.message,
    stack: error.stack
  }));
  process.exit(1);
}
