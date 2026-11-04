const {pw,exe,OUT}=require('./lib.cjs');
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  const errs=[];p.on('pageerror',e=>errs.push(String(e)));
  const sizes=[{width:1440,height:900},{width:1024,height:768},{width:390,height:844},{width:320,height:700}];
  const measure=()=>p.evaluate(()=>{
    const c=document.querySelector('canvas').getBoundingClientRect();
    const side=document.querySelector('#side-panel');
    return {vw:innerWidth,vh:innerHeight,canvasW:Math.round(c.width),canvasH:Math.round(c.height),
      scrollW:document.documentElement.scrollWidth,overflowX:document.documentElement.scrollWidth>innerWidth+1,
      canvasCount:document.querySelectorAll('canvas').length,
      sideVisible:!!(side&&side.getBoundingClientRect().width>0),
      topbarOverflow:document.querySelector('.od-topbar__right').getBoundingClientRect().right>innerWidth+1,
      impulseVisible:!!document.querySelector('input, textarea')};
  });
  const out=[];
  for(const s of sizes){
    await p.setViewportSize(s);
    await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
    await p.locator('canvas').first().waitFor({state:'attached'});
    await p.waitForTimeout(1400);
    const m0=await measure();
    let m1=null;
    const collapse=p.locator('[aria-label="收起侧栏"]');
    if(await collapse.count() && await collapse.first().isVisible()){ await collapse.first().click(); await p.waitForTimeout(900); m1=await measure(); }
    let m2=null;
    if(await p.locator('#saves-toggle').count()){ await p.locator('#saves-toggle').click(); await p.waitForTimeout(800); m2=await measure(); }
    let m3=null;
    if(await p.locator('[aria-label="收起侧栏"]').count()){ await p.locator('[aria-label="收起侧栏"]').first().click(); await p.waitForTimeout(700); m3=await measure(); }
    out.push({size:s,initial:m0,afterCollapse:m1,savesOpen:m2,savesClosed:m3});
    await p.screenshot({path:OUT+`N-${s.width}.png`});
  }
  for(const o of out) console.log(JSON.stringify(o));
  console.log('errors',JSON.stringify(errs));
  await b.close();
})();
