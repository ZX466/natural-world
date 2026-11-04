const {pw,exe,OUT}=require('./lib.cjs');
const ZOOM=3.5,TW=32,TH=16,HH=16;
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  const errs=[];p.on('pageerror',e=>errs.push(String(e)));
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.waitForTimeout(2000);
  const snap=()=>p.evaluate(async()=>{const {worldMirror}=await import('/src/game/runtime.ts');const {useUiStore}=await import('/src/store/uiStore.ts');const a=worldMirror.actors.get(worldMirror.protagonist??'');const r=document.querySelector('canvas').getBoundingClientRect();return{x:a.x,y:a.y,cx:r.left+r.width/2,cy:r.top+r.height/2,inv:useUiStore.getState().voxelInventory,err:useUiStore.getState().voxelError};});
  const proj=(s,x,y,h=1)=>({x:s.cx+((x-s.x)-(y-s.y))*(TW/2)*ZOOM,y:s.cy+((x-s.x)+(y-s.y))*(TH/2)*ZOOM-(h-1)*HH*ZOOM});
  const hud=()=>p.evaluate(()=>{const el=document.querySelector('[aria-label="行囊"]');return el?el.innerText.replace(/\n/g,' | '):null;});
  const idle=async()=>{let prev=null,same=0;for(let i=0;i<60;i++){const s=await snap();if(prev&&s.x===prev.x&&s.y===prev.y){same++;if(same>=8)return s;}else same=0;prev=s;await p.waitForTimeout(50);}return prev;};

  const results=[];
  // 找三类材料（各自最近、可达：在 4 格内且为阻挡格）
  const findMat=async(mat)=>p.evaluate(async({mat})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const iso=await import('/src/game/render/iso.ts');
    const m=worldMirror.map,a=worldMirror.actors.get(worldMirror.protagonist??'');
    const heightAt=iso.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    const want={earth:1,stone:2,wood:3}[mat];
    let best=null,bd=99;
    for(let dy=-4;dy<=4;dy++)for(let dx=-4;dx<=4;dx++){
      const x=a.x+dx,y=a.y+dy;if(x<0||y<0||x>=m.w||y>=m.h)continue;
      const i=y*m.w+x;if(m.collision[i]!==0)continue;
      if(heightAt(x,y)!==want)continue;
      const d=Math.abs(dx)+Math.abs(dy);if(d>4)continue;
      if(d<bd){bd=d;best={x,y,h:want};}
    }
    return best;
  },{mat});

  for(const mat of ['earth','stone','wood']){
    let s=await idle();
    let t=await findMat(mat);
    if(!t){results.push([mat,'无 4 格内样本']);continue;}
    const pt=proj(s,t.x,t.y,t.h);
    await p.mouse.move(pt.x,pt.y);await p.mouse.down();await p.waitForTimeout(1300);await p.mouse.up();
    await p.waitForTimeout(2200);
    s=await snap();
    results.push([mat,`格 ${t.x},${t.y} h=${t.h} → 行囊 ${JSON.stringify(s.inv)} 错误 ${JSON.stringify(s.err)} HUD ${JSON.stringify(await hud())}`]);
  }
  for(const [k,v] of results) console.log(`${k} :: ${v}`);
  console.log('errors',JSON.stringify(errs));
  await p.screenshot({path:OUT+'G-three-materials.png'});
  await b.close();
})();
