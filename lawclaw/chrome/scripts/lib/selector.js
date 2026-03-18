/**
 * Shared selector parsing and validation library.
 * Supports CSS and XPath selectors with security validation.
 */

const ALLOWED_XPATH_AXES = [
  'ancestor', 'ancestor-or-self', 'attribute', 'child', 'descendant',
  'descendant-or-self', 'following', 'following-sibling', 'namespace',
  'parent', 'preceding', 'preceding-sibling', 'self'
];

const ALLOWED_XPATH_FUNCTIONS = [
  'text', 'contains', 'starts-with', 'normalize-space', 'string-length',
  'concat', 'substring', 'substring-before', 'substring-after', 'translate',
  'not', 'true', 'false', 'boolean', 'string', 'number', 'sum', 'floor',
  'ceiling', 'round', 'count', 'name', 'local-name', 'namespace-uri',
  'last', 'position', 'id', 'lang', 'comment', 'processing-instruction', 'node'
];

export function parseSelector(selector) {
  if (!selector || typeof selector !== 'string') {
    throw new Error('Selector must be a non-empty string');
  }
  if (selector.startsWith('/') || selector.startsWith('(//')) {
    validateXPath(selector);
    return { type: 'xpath', selector };
  }
  validateCSS(selector);
  return { type: 'css', selector };
}

function validateXPath(xpath) {
  if (xpath.length > 1000) throw new Error('XPath selector too long (max 1000 characters)');
  const predicateCount = (xpath.match(/\[/g) || []).length;
  if (predicateCount > 10) throw new Error('XPath too complex: max 10 predicates allowed');

  const functionPattern = /([a-z][a-z0-9-]*)\s*\(/gi;
  let match;
  while ((match = functionPattern.exec(xpath)) !== null) {
    const funcName = match[1].toLowerCase();
    if (!ALLOWED_XPATH_FUNCTIONS.includes(funcName)) {
      throw new Error(`XPath function not allowed: ${funcName}`);
    }
  }

  const axisPattern = /([a-z][a-z-]*)::/gi;
  while ((match = axisPattern.exec(xpath)) !== null) {
    const axisName = match[1].toLowerCase();
    if (!ALLOWED_XPATH_AXES.includes(axisName)) {
      throw new Error(`XPath axis not allowed: ${axisName}`);
    }
  }

  if (/^https?:\/\//i.test(xpath)) throw new Error('XPath cannot be a URL');
  if (/<[a-z]/i.test(xpath)) throw new Error('XPath cannot contain HTML tags');
}

function validateCSS(css) {
  if (css.length > 500) throw new Error('CSS selector too long (max 500 characters)');
  const selectorParts = css.split(/\s*,\s*/);
  if (selectorParts.length > 10) throw new Error('CSS selector too complex: max 10 comma-separated selectors');
  if (/^https?:\/\//i.test(css)) throw new Error('CSS selector cannot be a URL');
  if (/<[a-z]/i.test(css)) throw new Error('CSS selector cannot contain HTML tags');
  if (/url\s*\(/i.test(css)) throw new Error('CSS selector cannot contain url()');
}

export async function waitForElement(page, parsed, options = {}) {
  const opts = { visible: true, timeout: 5000, ...options };
  if (parsed.type === 'xpath') {
    const locator = page.locator(`::-p-xpath(${parsed.selector})`);
    await locator.setVisibility(opts.visible ? 'visible' : null).setTimeout(opts.timeout).wait();
  } else {
    await page.waitForSelector(parsed.selector, opts);
  }
}

export async function clickElement(page, parsed) {
  if (parsed.type === 'xpath') {
    await page.locator(`::-p-xpath(${parsed.selector})`).click();
  } else {
    await page.click(parsed.selector);
  }
}

export async function typeIntoElement(page, parsed, value, options = {}) {
  if (parsed.type === 'xpath') {
    const locator = page.locator(`::-p-xpath(${parsed.selector})`);
    if (options.clear) await locator.fill('');
    await locator.fill(value);
  } else {
    if (options.clear) await page.$eval(parsed.selector, el => el.value = '');
    await page.type(parsed.selector, value, { delay: options.delay || 0 });
  }
}

export async function getElement(page, parsed) {
  if (parsed.type === 'xpath') {
    const element = await page.evaluateHandle((xpath) => {
      const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      return result.singleNodeValue;
    }, parsed.selector);
    return element.asElement();
  }
  return await page.$(parsed.selector);
}

export function enhanceError(error, selector) {
  if (error.message.includes('waiting for selector') ||
      error.message.includes('waiting for XPath') ||
      error.message.includes('No node found')) {
    error.message += '\n\nTroubleshooting:\n' +
      '1. Try XPath: //button[text()="Click"] or //button[contains(text(),"Click")]\n' +
      '2. Check element is visible (not display:none or hidden)\n' +
      '3. Increase --timeout value\n' +
      '4. Change wait strategy: --wait-until load or domcontentloaded';
  }
  return error;
}
