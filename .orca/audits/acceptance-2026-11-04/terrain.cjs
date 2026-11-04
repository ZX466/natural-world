const {pw,exe,OUT}=require('./lib.cjs');
const fs=require('node:fs');
const ZOOM=3.5,TW=32,TH=16;
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  const errs=[];p.on('pageerror',e=>errs.push(String(e)));
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.waitForTimeout(1500);
  const snap=()=>p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const {useUiStore}=await import('/src/store/uiStore.ts');
    const a=worldMirror.actors.get(worldMirror.protagonist??'');
    const r=document.querySelector('canvas').getBoundingClientRect();
    return {x:a.x,y:a.y,cx:r.left+r.width/2,cy:r.top+r.height/2,err:useUiStore.getState().voxelError};
  });
  const proj=(s,x,y,h=1)=>({x:s.cx+((x-s.x)-(y-s.y))*(TW/2)*ZOOM,y:s.cy+((x-s.x)+(y-s.y))*(TH/2)*ZOOM-(h-1)*TH*ZOOM});
  const idle=async(ms=700)=>{let prev=null,same=0;const t=Date.now();
    while(Date.now()-t<ms+2000){const s=await snap();if(prev&&s.x===prev.x&&s.y===prev.y){same+=50;if(same>=ms)return s;}else same=0;prev=s;await p.waitForTimeout(50);}return prev;};
  const out=[];

  // ---- 地图统计（真实数据）----
  const stats=await p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const m=worldMirror.map;
    const h=await import('/src/game/render/iso.ts');
    const heightAt=h.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    let walk=0,block=0,bank=0,water=0,high=0;
    for(let y=0;y<m.h;y++)for(let x=0;x<m.w;x++){
      const i=y*m.w+x;const hh=heightAt(x,y);
      if(hh===0){water++;continue;}
      if(m.collision[i]===1)walk++;
      else{block++;if(hh===1)bank++;else high++;}
    }
    return {w:m.w,h:m.h,walk,block,bank,high,water,total:m.w*m.h};
  });
  out.push({k:'地形分类',v:JSON.stringify(stats)});

  // ---- 6. 挡路：点河面 / 点房子 → 应拒绝并给戏内提示 ----
  const targets=await p.evaluate(async({x,y})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const m=worldMirror.map;
    const h=await import('/src/game/render/iso.ts');
    const heightAt=h.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    const near=[];const bankPts=[];
    for(let dy=-8;dy<=8;dy++)for(let dx=-8;dx<=8;dx++){
      const nx=x+dx,ny=y+dy;if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
      const i=ny*m.w+nx;const hh=heightAt(nx,ny);
      if(m.collision[i]===0&&hh>=2) near.push({x:nx,y:ny,kind:'house'});
      if(m.collision[i]===0&&hh===0) near.push({x:nx,y:ny,kind:'water'});
      if(m.collision[i]===0&&hh===1) bankPts.push({x:nx,y:ny,kind:'bank'});
    }
    return {near:near.slice(0,2),banks:bankPts.slice(0,3)};
  },{x:0,y:0});
  out.push({k:'出生点 17×17 内阻挡样本',v:JSON.stringify(targets.near.slice(0,2))+' / 土坎样本 '+JSON.stringify(targets.banks)});
  await b.close();
  for(const r of out) console.log(`${r.k} :: ${r.v}`);
})();
