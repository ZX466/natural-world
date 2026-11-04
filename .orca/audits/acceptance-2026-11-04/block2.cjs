const {pw,exe}=require('./lib.cjs');
const ZOOM=3.5,TW=32,TH=16,HH=16;
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.waitForTimeout(1500);
  const snap=()=>p.evaluate(async()=>{const {worldMirror}=await import('/src/game/runtime.ts');const {useUiStore}=await import('/src/store/uiStore.ts');const a=worldMirror.actors.get(worldMirror.protagonist??'');const r=document.querySelector('canvas').getBoundingClientRect();return{x:a.x,y:a.y,cx:r.left+r.width/2,cy:r.top+r.height/2,err:useUiStore.getState().voxelError};});
  const proj=(s,x,y,h=1)=>({x:s.cx+((x-s.x)-(y-s.y))*(TW/2)*ZOOM,y:s.cy+((x-s.x)+(y-s.y))*(TH/2)*ZOOM-(h-1)*HH*ZOOM});
  // 用 pickGround 直接验证：点某阻挡格顶面中心 → pickGround 应为 null（拒走）
  const r=await p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const iso=await import('/src/game/render/iso.ts');
    const pick=await import('/src/game/render/voxel-picking.ts');
    const m=worldMirror.map,a=worldMirror.actors.get(worldMirror.protagonist??'');
    const heightAt=iso.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    const bounds=iso.screenBounds(m.w,m.h);
    const walk=(x,y)=>m.collision[y*m.w+x]===1;
    let tested=0,refused=0,waterTested=0,waterRefused=0;
    for(let dy=-12;dy<=12;dy++)for(let dx=-12;dx<=12;dx++){
      const x=a.x+dx,y=a.y+dy;if(x<0||y<0||x>=m.w||y>=m.h)continue;
      const i=y*m.w+x;if(m.collision[i]===1)continue;
      const hh=heightAt(x,y);
      const t=iso.isoProject(x,y,Math.max(hh,1),bounds);
      const g=pick.pickGround(t.sx,t.sy,m.w,m.h,heightAt,walk);
      tested++; if(g===null)refused++;
      if(hh===0){waterTested++;if(g===null)waterRefused++;}
    }
    return {blockedCells:tested,groundRefused:refused,waterCells:waterTested,waterRefused};
  });
  console.log('阻挡格 25×25 邻域',JSON.stringify(r));
  // 真点击一次水面
  let s=await snap();
  const w=await p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const iso=await import('/src/game/render/iso.ts');
    const m=worldMirror.map,a=worldMirror.actors.get(worldMirror.protagonist??'');
    const heightAt=iso.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    for(let dy=-10;dy<=10;dy++)for(let dx=-10;dx<=10;dx++){
      const x=a.x+dx,y=a.y+dy;if(x<0||y<0||x>=m.w||y>=m.h)continue;
      if(m.collision[y*m.w+x]===0&&heightAt(x,y)===0) return {x,y};
    }
    return null;
  });
  if(w){const pt=proj(s,w.x,w.y,0);await p.mouse.click(pt.x,pt.y);await p.waitForTimeout(600);s=await snap();
    console.log(`点水面 ${w.x},${w.y} → 提示 ${JSON.stringify(s.err)}，人物仍在 ${s.x},${s.y}`);}
  await b.close();
})();
