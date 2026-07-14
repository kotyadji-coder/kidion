const { test, expect } = require('@playwright/test');

const baseURL = process.env.BASE_URL || 'https://chat.kidion.ru';

test.use({
  viewport: { width: 390, height: 844 },
  userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Mobile Safari/537.36',
  isMobile: true,
  hasTouch: true,
});

async function pageDiagnostics(page) {
  return page.evaluate(() => {
    const vw = window.innerWidth;
    const offenders = [];
    for (const el of Array.from(document.querySelectorAll('body *'))) {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden') continue;
      if (rect.right - vw > 1 || rect.left < -1) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          cls: typeof el.className === 'string' ? el.className : '',
          text: (el.innerText || el.alt || '').trim().replace(/\s+/g, ' ').slice(0, 60),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          viewport: vw,
        });
      }
    }
    return {
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      offenders,
    };
  });
}

test('chat landing is PWA-ready on Android', async ({ page, context }) => {
  const consoleErrors = [];
  const failedRequests = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('requestfailed', (request) => {
    failedRequests.push(`${request.url()} ${request.failure()?.errorText || ''}`);
  });

  await page.goto(baseURL, { waitUntil: 'networkidle' });
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.json');
  await expect(page.locator('script[src^="/static/spark/pwa.js"]')).toHaveCount(1);

  const manifest = await page.request.get(`${baseURL.replace(/\/$/, '')}/manifest.json`);
  expect(manifest.ok()).toBeTruthy();
  const data = await manifest.json();
  expect(data.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ sizes: '192x192' }),
    expect.objectContaining({ sizes: '512x512' }),
  ]));

  await page.waitForTimeout(1000);
  const swCount = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) return -1;
    return (await navigator.serviceWorker.getRegistrations()).length;
  });
  expect(swCount).toBeGreaterThan(0);

  const cdp = await context.newCDPSession(page);
  const installability = await cdp.send('Page.getInstallabilityErrors');
  expect(installability.installabilityErrors).toEqual([]);

  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});

test('chat landing does not overflow on 360px Android', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 844 });
  await page.goto(baseURL, { waitUntil: 'networkidle' });
  const diagnostics = await pageDiagnostics(page);
  expect(diagnostics.scrollWidth).toBeLessThanOrEqual(diagnostics.innerWidth);
  expect(diagnostics.offenders).toEqual([]);
});

test('login page keeps PWA metadata after /chat redirect', async ({ page }) => {
  await page.goto(`${baseURL.replace(/\/$/, '')}/chat`, { waitUntil: 'networkidle' });
  await expect(page).toHaveURL(/\/chat\/login$/);
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.json');
  await expect(page.locator('script[src^="/static/spark/pwa.js"]')).toHaveCount(1);
});
