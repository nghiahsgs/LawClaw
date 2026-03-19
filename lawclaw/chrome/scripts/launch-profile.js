#!/usr/bin/env node
/**
 * Launch Chromium with a persistent profile.
 * Uses Puppeteer's bundled Chromium — no Chrome restrictions, no Keychain issues.
 *
 * Profiles stored at: ~/.lawclaw/workspace/chrome/profiles/{name}/
 * State files at: ~/.lawclaw/workspace/chrome/
 */
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import os from 'os';

const CHROME_DIR = path.join(os.homedir(), '.lawclaw', 'workspace', 'chrome');
const PROFILES_DIR = path.join(CHROME_DIR, 'profiles');
const ENDPOINT_FILE = path.join(CHROME_DIR, '.browser-endpoint');
const PROFILE_META_FILE = path.join(CHROME_DIR, '.profile-meta');

// Parse args
const args = process.argv.slice(2);
const getArg = (name) => {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1) return null;
  if (idx + 1 >= args.length || args[idx + 1].startsWith('--')) return true;
  return args[idx + 1];
};

const profileName = getArg('name');
const url = getArg('url');
const headless = getArg('headless') !== 'false' && !args.includes('--no-headless');
const listMode = getArg('list');

// Ensure dirs exist
fs.mkdirSync(PROFILES_DIR, { recursive: true });

// --list: show saved profiles
if (listMode) {
  const dirs = fs.readdirSync(PROFILES_DIR).filter(d =>
    fs.statSync(path.join(PROFILES_DIR, d)).isDirectory()
  );
  const result = {
    success: true,
    profiles: dirs.map(d => {
      const stat = fs.statSync(path.join(PROFILES_DIR, d));
      return { name: d, lastUsed: stat.mtime.toISOString() };
    })
  };
  // Check active profile
  if (fs.existsSync(PROFILE_META_FILE)) {
    try {
      result.active = JSON.parse(fs.readFileSync(PROFILE_META_FILE, 'utf8'));
    } catch {}
  }
  console.log(JSON.stringify(result));
  process.exit(0);
}

if (!profileName) {
  console.log(JSON.stringify({ success: false, error: '--name is required' }));
  process.exit(1);
}

async function main() {
  // Check if already running
  if (fs.existsSync(ENDPOINT_FILE)) {
    try {
      const ws = fs.readFileSync(ENDPOINT_FILE, 'utf8').trim();
      const browser = await puppeteer.connect({ browserWSEndpoint: ws });
      // Check if same profile
      if (fs.existsSync(PROFILE_META_FILE)) {
        const meta = JSON.parse(fs.readFileSync(PROFILE_META_FILE, 'utf8'));
        if (meta.profileName === profileName) {
          console.log(JSON.stringify({
            success: true,
            message: `Profile "${profileName}" already running`,
            wsEndpoint: ws,
            profileName: meta.profileName,
            headless: meta.headless
          }));
          browser.disconnect();
          process.exit(0);
        }
      }
      // Different profile running
      console.log(JSON.stringify({
        success: false,
        error: 'Another profile is running. Stop it first.'
      }));
      browser.disconnect();
      process.exit(1);
    } catch {
      fs.unlinkSync(ENDPOINT_FILE);
    }
  }

  const profileDir = path.join(PROFILES_DIR, profileName);
  const isNew = !fs.existsSync(profileDir);
  if (isNew) fs.mkdirSync(profileDir, { recursive: true });

  const browser = await puppeteer.launch({
    headless,
    userDataDir: profileDir,
    args: [
      '--no-first-run',
      '--no-default-browser-check',
      '--remote-allow-origins=*',
      '--disable-background-timer-throttling',
      '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding',
    ],
    defaultViewport: headless ? { width: 1920, height: 1080 } : null,
  });

  const wsEndpoint = browser.wsEndpoint();

  fs.writeFileSync(ENDPOINT_FILE, wsEndpoint);
  fs.writeFileSync(PROFILE_META_FILE, JSON.stringify({
    profileName,
    profileDir,
    headless,
    launchedAt: new Date().toISOString(),
  }));

  if (url) {
    const page = (await browser.pages())[0] || await browser.newPage();
    await page.goto(url, { waitUntil: 'networkidle2' });
  }

  console.log(JSON.stringify({
    success: true,
    message: `Browser launched with profile "${profileName}"`,
    profileName,
    profileDir,
    headless,
    isNew,
    wsEndpoint
  }));

  // Graceful shutdown
  const cleanup = async () => {
    try { await browser.close(); } catch {}
    try { fs.unlinkSync(ENDPOINT_FILE); } catch {}
    try { fs.unlinkSync(PROFILE_META_FILE); } catch {}
    process.exit(0);
  };

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);

  // Keep alive
  await new Promise(() => {});
}

main().catch(error => {
  console.log(JSON.stringify({ success: false, error: error.message }));
  process.exit(1);
});
