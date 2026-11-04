const {pw,exe,OUT}=require('./lib.cjs');
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  // 加速到 16x，采样 3 分钟实时（≈48 游戏分）
  await p.locator('.od-speed__btn').nth(2).click();
  const seen=new Map();
  const t0=Date.now();
  while(Date.now()-t0<180000){
    const rows=await p.evaluate(async()=>{
      const {useUiStore}=await import('/src/store/uiStore.ts');
      return useUiStore.getState().chatter.map(c=>({name:c.name,content:c.content}));
    });
    for(const r of rows) if(!seen.has(r.content+r.name)) seen.set(r.content+r.name,r);
    await p.waitForTimeout(1500);
  }
  const all=[...seen.values()];
  const retells=all.filter(c=>/^听.*说，/.test(c.content));
  const selfNamed=retells.filter(c=>{const m=/^听(.+?)说，(.+)$/.exec(c.content);return m&&m[1]===c.name;});
  console.log('去重 chatter 条数',all.length,'；转述',retells.length,'；转述人称=转述者自己',selfNamed.length);
  console.log(JSON.stringify(retells.slice(0,12),null,1));
  console.log('--- 判定：', selfNamed.length===retells.length ? '全部转述都把说话人记成转述者自己（系统性）' : `${selfNamed.length}/${retells.length} 自指`);
  await b.close();
})();
