const {pw,exe,OUT}=require('./lib.cjs');
const fs=require('node:fs');
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  const errs=[];p.on('pageerror',e=>errs.push(String(e)));
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.waitForTimeout(1200);
  const st=async()=>p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const a=worldMirror.actors.get(worldMirror.protagonist??'');
    const c=document.querySelector('canvas').getBoundingClientRect();
    const err=await import('/src/store/uiStore.ts');
    return {x:a.x,y:a.y,cx:c.left+c.width/2,cy:c.top+c.height/2,
      voxelError:err.useUiStore.getState().voxelError};
  });
  const ZOOM=3.5,TW=32,TH=16,HH=16;
  const mk=(s)=>(x,y,h=1)=>({x:s.cx+((x-s.x)-(y-s.y))*(TW/2)*ZOOM, y:s.cy+((x-s.x)+(y-s.y))*(TH/2)*ZOOM-(h-1)*HH*ZOOM});
  const walkPath=async(from,n)=>p.evaluate(async({from,n})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const m=worldMirror.map; const out=[]; let {x,y}=from;
    for(let i=0;i<n;i++){
      let step=null;
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]){
        const nx=x+dx,ny=y+dy;
        if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
        if(m.collision[ny*m.w+nx]!==1)continue;
        if(dx&&dy&&(m.collision[y*m.w+nx]!==1||m.collision[ny*m.w+x]!==1))continue;
        step={x:nx,y:ny};break;
      }
      if(!step)break; out.push(step); x=step.x;y=step.y;
    }
    return out;
  },{from:{x:from.x,y:from.y},n});

  const results=[];
  const add=(k,v)=>results.push([k,v]);

  // 1) 单击
  let s=await st(); const P=mk(s);
  const w1=await walkPath(s,1);
  const t0=Date.now();
  await p.mouse.click(P(w1[0].x,w1[0].y).x,P(w1[0].x,w1[0].y).y);
  await p.waitForTimeout(800);
  let s1=await st();
  add('单击走一格', `${s.x},${s.y} -> ${s1.x},${s1.y} (期望 ${w1[0].x},${w1[0].y})`);

  // 2) 拖拽（按住划过多格）
  s=await st(); const P2=mk(s);
  const path=await walkPath(s,5);
  if(path.length>=4){
    const a=P2(path[0].x,path[0].y), d=P2(path[3].x,path[3].y);
    await p.mouse.move(a.x,a.y); await p.mouse.down();
    for(const q of path.slice(0,4)){ const pt=P2(q.x,q.y); await p.mouse.move(pt.x,pt.y,{steps:3}); await p.waitForTimeout(90);}
    await p.mouse.up(); await p.waitForTimeout(1500);
    s1=await st();
    add('拖拽连走', `${s.x},${s.y} -> ${s1.x},${s1.y} (目标 ${path[3].x},${path[3].y})`);
  } else add('拖拽连走','无足够可走路径');

  // 3) 键盘
  s=await st();
  await p.locator('canvas').first().click({position:{x:50,y:50}});
  await p.waitForTimeout(400);
  s=await st();
  const kb0=s;
  await p.keyboard.down('KeyD'); await p.waitForTimeout(700); await p.keyboard.up('KeyD');
  await p.waitForTimeout(600);
  s1=await st();
  add('键盘 D 走一步', `${kb0.x},${kb0.y} -> ${s1.x},${s1.y}`);

  // 4) 长按挖（先走到土坎旁）— 用 edit 拾取点高块
  s=await st(); const P3=mk(s);
  const diggable=await p.evaluate(async({x,y})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const m=worldMirror.map; const h=await import('/src/game/render/iso.ts');
    const out=[];
    for(let dy=-4;dy<=4;dy++)for(let dx=-4;dx<=4;dx++){
      const nx=x+dx,ny=y+dy;
      if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
      if(m.collision[ny*m.w+nx]===0 && Math.abs(dx)+Math.abs(dy)<=4) out.push({x:nx,y:ny});
    }
    return out.slice(0,6);
  },{x:s.x,y:s.y});
  add('附近可挖格数', String(diggable.length));

  // 5) Escape 取消移动
  s=await st(); const P4=mk(s);
  const far=await walkPath(s,8);
  if(far.length>=6){
    const t=P4(far[5].x,far[5].y);
    await p.mouse.click(t.x,t.y);
    await p.waitForTimeout(300);
    await p.keyboard.press('Escape');
    await p.waitForTimeout(900);
    s1=await st();
    add('Escape 取消移动', `${s.x},${s.y} -> ${s1.x},${s1.y}（未跑满 ${far[5].x},${far[5].y} 即算生效）`);
  } else add('Escape 取消移动','无长路径');

  add('页面异常', JSON.stringify(errs));
  for(const [k,v] of results) console.log(`${k} :: ${v}`);
  fs.writeFileSync(OUT+'feel.json',JSON.stringify(results,null,2));
  await p.screenshot({path:OUT+'B-after-move.png'});
  await b.close();
})();
