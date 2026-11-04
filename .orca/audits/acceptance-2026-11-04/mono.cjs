const {pw,exe}=require('./lib.cjs');
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.locator('.od-speed__btn').nth(2).click(); // 16x
  const seen=new Set(); const t0=Date.now();
  while(Date.now()-t0<150000){
    const rows=await p.evaluate(async()=>{
      const {useUiStore}=await import('/src/store/uiStore.ts');
      const s=useUiStore.getState();
      return {mono:s.monologues.map(m=>m.content),clock:s.gameClock,paused:s.paused};
    });
    rows.mono.forEach(m=>seen.add(m));
    await p.waitForTimeout(1200);
  }
  console.log('心声去重条数',seen.size);
  console.log(JSON.stringify([...seen].slice(0,20),null,1));
  const panel=await p.evaluate(()=>{const el=document.querySelector('.od-panel--voice');return el?el.innerText:null;});
  console.log('面板文本',JSON.stringify(panel));
  await b.close();
})();
