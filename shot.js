const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const ctx = await b.newContext({ viewport: { width: 1500, height: 950 }, deviceScaleFactor: 2, colorScheme: 'dark' });
  const p = await ctx.newPage();
  await p.goto('http://127.0.0.1:8080/login', { waitUntil: 'networkidle' });
  await p.fill('input[name=email]', 'prajwal@example.com');
  await p.fill('input[name=password]', 'a good long phrase');
  await p.click('button[type=submit]');
  await p.waitForLoadState('networkidle');

  await p.goto('http://127.0.0.1:8080/?view=focus&state=IN_PROGRESS', { waitUntil: 'networkidle' });
  await p.waitForTimeout(1200);
  await p.screenshot({ path: '/tmp/pgs/v5-focus.png' });

  await p.goto('http://127.0.0.1:8080/absence', { waitUntil: 'networkidle' });
  await p.waitForTimeout(1200);
  await p.screenshot({ path: '/tmp/pgs/v5-absence.png', fullPage: true });

  await p.goto('http://127.0.0.1:8080/people', { waitUntil: 'networkidle' });
  await p.waitForTimeout(900);
  await p.click('[data-settings]');
  await p.waitForTimeout(700);
  await p.screenshot({ path: '/tmp/pgs/v5-settings.png' });

  await b.close();
  console.log('done');
})();
