/* 转述归因复验（修后）：与 retell.cjs 同口径，断言「听X说」的 X ≠ 转述者。 */
const { pw, exe } = require('./lib.cjs');

(async () => {
  const browser = await pw.chromium.launch({ headless: true, executablePath: exe });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });
  await page.waitForFunction(
    () => {
      const d = document.querySelector('.od-status');
      return d && d.getAttribute('aria-label') === '连接正常';
    },
    { timeout: 20000 },
  );
  await page.locator('.od-speed__btn').nth(2).click(); // 16x

  const seen = new Map();
  const t0 = Date.now();
  while (Date.now() - t0 < 180000) {
    const rows = await page.evaluate(async () => {
      const { useUiStore } = await import('/src/store/uiStore.ts');
      return useUiStore.getState().chatter.map((c) => ({ name: c.name, content: c.content }));
    });
    for (const r of rows) seen.set(`${r.content}|${r.name ?? ''}`, r);
    await page.waitForTimeout(1500);
  }

  const all = [...seen.values()];
  const retells = all.filter((c) => /^听.+?说，/.test(c.content));
  const selfNamed = retells.filter((c) => {
    const m = /^听(.+?)说，(.+)$/.exec(c.content);
    return m && m[1] === c.name;
  });
  console.log(`去重 chatter ${all.length}；转述 ${retells.length}；其中说话人=转述者自己 ${selfNamed.length}`);
  console.log('样本:', JSON.stringify(retells.slice(0, 10), null, 1));
  console.log(selfNamed.length === 0 ? 'PASS 归因正确' : `FAIL 仍自指 ${selfNamed.length} 条`);
  if (selfNamed.length) process.exitCode = 1;
  await browser.close();
})();
