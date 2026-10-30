/* Local visual regression. Requires the isolated preview on 5173/8000. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const browserRoot = 'C:/Users/zx198/AppData/Local/ms-playwright';
const links = path.join(browserRoot, '.links');
const library = fs.readdirSync(links).map(name => fs.readFileSync(path.join(links, name), 'utf8').trim())
  .find(dir => fs.existsSync(path.join(dir, 'package.json')) && require(dir).chromium);
assert(library, 'No existing linked Playwright library');
const playwright = require(library);
const executable = path.join(browserRoot, 'chromium-1248/chrome-win64/chrome.exe');
assert(path.resolve(executable).toLowerCase().startsWith(path.resolve(browserRoot).toLowerCase() + path.sep));
const baseline = process.argv.includes('--baseline');
const label = baseline ? 'red' : 'after';
const sizes = [{width:1440,height:900},{width:1024,height:768},{width:390,height:844}];

async function main() {
  const browser = await playwright.chromium.launch({headless:true,executablePath:executable});
  const context = await browser.newContext({viewport:sizes[0],deviceScaleFactor:1,locale:'zh-CN'});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const layouts = [], failures = [];
  try {
    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
      await page.locator('canvas').first().waitFor({state:'attached'});
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const layout = await page.evaluate(() => {
        const canvas = document.querySelector('canvas').getBoundingClientRect();
        const parent = document.querySelector('canvas').parentElement.getBoundingClientRect();
        const save = document.querySelector('.od-menu--saveload');
        const visible = save && save.getBoundingClientRect().width > 0;
        return {width:innerWidth,height:innerHeight,canvasWidth:canvas.width,canvasHeight:canvas.height,parentWidth:parent.width,parentHeight:parent.height,canvasCount:document.querySelectorAll('canvas').length,scrollWidth:document.documentElement.scrollWidth,saveVisible:!!visible,hasJournalToggle:!!document.querySelector('#journal-toggle'),hasSaveToggle:!!document.querySelector('#saves-toggle')};
      });
      layouts.push(layout);
      if (layout.canvasWidth < size.width * (size.width < 900 ? .95 : .70)) failures.push(`${size.width}: canvas squeezed to ${layout.canvasWidth}`);
      if (layout.canvasHeight < size.height * .6) failures.push(`${size.width}: canvas too short`);
      if (Math.abs(layout.canvasWidth-layout.parentWidth)>1 || Math.abs(layout.canvasHeight-layout.parentHeight)>1) failures.push(`${size.width}: canvas does not fill its container`);
      if (layout.scrollWidth > size.width) failures.push(`${size.width}: horizontal overflow`);
      if (layout.canvasCount !== 1) failures.push(`${size.width}: duplicate game canvas`);
      if (layout.saveVisible) failures.push(`${size.width}: empty save column permanently visible`);
      if (!layout.hasJournalToggle || !layout.hasSaveToggle) failures.push(`${size.width}: panel controls missing`);
      await page.screenshot({path:path.join(__dirname,`${label}-${size.width}.png`),fullPage:true});
    }
    fs.writeFileSync(path.join(__dirname,`${label}-layout.json`), JSON.stringify({layouts,failures,errors},null,2)+'\n');
    assert.deepEqual(failures,[],'Responsive layout regressions');
    assert.deepEqual(errors,[],'Browser errors');
    if (baseline) return;

    await page.setViewportSize(sizes[0]);
    await page.reload({waitUntil:'networkidle'});
    const desktopWidth = (await page.locator('canvas').boundingBox()).width;
    await page.getByRole('button',{name:'存档',exact:true}).click();
    await page.getByRole('button',{name:'存一档',exact:true}).waitFor({state:'visible'});
    assert.equal((await page.locator('canvas').boundingBox()).width,desktopWidth,'Switching panels must not add a column');
    await page.getByRole('button',{name:'手札',exact:true}).click();
    await page.getByRole('heading',{name:'心之声',exact:true}).waitFor({state:'visible'});
    await page.getByRole('button',{name:'手札',exact:true}).click();
    await page.waitForFunction(() => document.querySelector('canvas').getBoundingClientRect().width === innerWidth);
    await page.getByRole('button',{name:'存档',exact:true}).click();
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.activeElement?.id === 'saves-toggle');
    assert.equal(await page.getByRole('button',{name:'存一档',exact:true}).count(),0);
    await page.getByRole('button',{name:'手札',exact:true}).click();
    const impulseInput = page.getByLabel('往陈默心里放一个念头',{exact:true});
    await impulseInput.focus();
    await page.evaluate(() => document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',isComposing:true,bubbles:true})));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert(await page.locator('#side-panel').isVisible(),'IME composition Escape must not close the journal');
    assert(await impulseInput.evaluate(node=>document.activeElement===node),'IME composition must retain input focus');
    await page.evaluate(async () => {
      const {useUiStore} = await import('/src/store/uiStore.ts');
      for(let i=0;i<30;i++) {
        useUiStore.getState().pushMonologue('thought',`沿着河岸慢慢走，听见桥那头有人说起今天的集市。${i}`.repeat(3));
        useUiStore.getState().pushChatter('桥边的人',`河水绕过石桥，天色又晚了一些。${i}`.repeat(3));
      }
    });
    const panels = await page.locator('.od-panel').evaluateAll(nodes=>nodes.map(node=>({height:node.clientHeight,scroll:node.scrollHeight,width:node.clientWidth,scrollWidth:node.scrollWidth})));
    assert(panels.every(panel=>panel.height>100&&panel.scroll>panel.height&&panel.scrollWidth<=panel.width),'Narrative panels must scroll independently without horizontal overflow');
    await page.screenshot({path:path.join(__dirname,'after-populated-1440.png'),fullPage:true});

    await page.setViewportSize(sizes[2]);
    await page.waitForFunction(() => document.getElementById('side-panel').hidden);
    await page.waitForFunction(() => document.querySelector('canvas').getBoundingClientRect().width === innerWidth);
    await page.reload({waitUntil:'networkidle'});
    await page.getByRole('button',{name:'存档',exact:true}).click();
    await page.getByRole('button',{name:'存一档',exact:true}).waitFor({state:'visible'});
    assert.equal((await page.locator('canvas').boundingBox()).width,390,'Compact drawer must overlay instead of squeeze the world');
    await page.screenshot({path:path.join(__dirname,'after-saves-390.png'),fullPage:true});
    await page.getByRole('button',{name:'关闭侧栏遮罩',exact:true}).click({position:{x:8,y:8}});
    await page.waitForFunction(() => document.activeElement?.id === 'saves-toggle');
    await page.getByRole('button',{name:'设置',exact:true}).click();
    await page.getByRole('heading',{name:'模型设置',exact:true}).waitFor({state:'visible'});
    const settings = await page.locator('.od-sheet').evaluate(node=>({width:node.clientWidth,scrollWidth:node.scrollWidth}));
    assert(settings.scrollWidth<=settings.width,'Settings must fit narrow screens');
    const fields = await page.locator('.od-sheet input').evaluateAll(nodes=>nodes.map(node=>({x:node.getBoundingClientRect().x,right:node.getBoundingClientRect().right})));
    assert(fields.every(field=>field.x>=0&&field.right<=390),'Settings fields outside viewport');
    await page.screenshot({path:path.join(__dirname,'after-settings-390.png'),fullPage:true});
    await page.getByRole('button',{name:'返回',exact:true}).click();
    await page.waitForFunction(() => document.activeElement?.id === 'settings-toggle');
    await page.route('**/api/settings/profiles',route=>route.fulfill({json:[{
      id:'layout-fixture',name:'布局检查：一个较长的配置名称用于验证换行',
      base_url:'https://example.invalid/a-long-path-for-layout-checking-only/v1',
      model:'layout-check-model-with-a-long-display-name',temperature:0.7,max_tokens:2048,
      active:true,api_key_hint:'•••• 已保存',
    }]}));
    await page.getByRole('button',{name:'设置',exact:true}).click();
    await page.getByText('布局检查：一个较长的配置名称用于验证换行',{exact:true}).waitFor({state:'visible'});
    const populatedSettings = await page.locator('.od-sheet').evaluate(node=>({width:node.clientWidth,scrollWidth:node.scrollWidth}));
    assert(populatedSettings.scrollWidth<=populatedSettings.width,'Configured settings overflow the compact viewport');
    const populatedFields = await page.locator('.od-sheet input').evaluateAll(nodes=>nodes.map(node=>node.getBoundingClientRect().right));
    assert(populatedFields.every(right=>right<=390),'Configured settings form outside viewport');
    await page.screenshot({path:path.join(__dirname,'after-settings-configured-390.png'),fullPage:true});
    await page.getByRole('button',{name:'返回',exact:true}).click();
    await page.waitForFunction(() => document.activeElement?.id === 'settings-toggle');
    assert.deepEqual(errors,[],'Browser errors');
    fs.writeFileSync(path.join(__dirname,'after-layout.json'),JSON.stringify({layouts,failures,errors,checks:['panel switch','collapse expands canvas','Escape focus return','IME composition Escape preserves input','long narrative scroll','compact breakpoint closes sidebar','mobile drawer','outside dismissal','empty mobile settings','configured mobile settings']},null,2)+'\n');
    console.log(JSON.stringify({layouts,errors,checks:'passed'}));
  } finally {
    await browser.close();
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
