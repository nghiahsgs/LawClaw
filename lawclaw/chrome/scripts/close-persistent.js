#!/usr/bin/env node
/**
 * Close the persistent browser (profile is preserved for reuse).
 */
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import os from 'os';

const CHROME_DIR = path.join(os.homedir(), '.lawclaw', 'chrome');
const ENDPOINT_FILE = path.join(CHROME_DIR, '.browser-endpoint');
const PROFILE_META_FILE = path.join(CHROME_DIR, '.profile-meta');

async function main() {
  if (!fs.existsSync(ENDPOINT_FILE)) {
    console.log(JSON.stringify({ success: true, message: 'No browser running.' }));
    process.exit(0);
  }

  const wsEndpoint = fs.readFileSync(ENDPOINT_FILE, 'utf8').trim();
  let profileName = null;
  if (fs.existsSync(PROFILE_META_FILE)) {
    try {
      profileName = JSON.parse(fs.readFileSync(PROFILE_META_FILE, 'utf8')).profileName;
    } catch {}
  }

  try {
    const browser = await puppeteer.connect({ browserWSEndpoint: wsEndpoint });
    await browser.close();
  } catch (error) {
    // Browser may already be closed
  }

  try { fs.unlinkSync(ENDPOINT_FILE); } catch {}
  try { fs.unlinkSync(PROFILE_META_FILE); } catch {}

  console.log(JSON.stringify({
    success: true,
    message: `Browser closed. Profile "${profileName || 'unknown'}" preserved.`
  }));
}

main();
