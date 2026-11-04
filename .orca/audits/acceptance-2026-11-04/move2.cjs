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
  const proj=(s,x,y,h=1)=>({x:s.cx+((x-s.x)-(y-s.y))*(TW/2)*ZOOM, y:s.cy+((x-s.x)+(y-s.y))*(TH/2)*ZOOM-(h-1)*TH*ZOOM});
  const idle=async(ms=900)=>{let prev=null,same=0;const t=Date.now();
    while(Date.now()-t<ms+2000){const s=await snap();if(prev&&s.x===prev.x&&s.y===prev.y){same+=50;if(same>=ms)return s;}else same=0;prev=s;await p.waitForTimeout(50);}return prev;};

  const out=[];
  // --- 1. 单击远处可走格（多格路径）---
  let s=await idle();
  const far=await p.evaluate(async({x,y})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const m=worldMirror.map;
    // BFS 取距 6 步的可走格
    const q=[[x,y,0]];const seen=new Set([y*m.w+x]);const hits=[];
    while(q.length){const [cx,cy,d]=q.shift();if(d===6){hits.push({x:cx,y:cy});continue;}
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]){
        const nx=cx+dx,ny=cy+dy;if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
        if(m.collision[ny*m.w+nx]!==1)continue;
        if(dx&&dy&&(m.collision[cy*m.w+nx]!==1||m.collision[ny*m.w+cx]!==1))continue;
        const k=ny*m.w+nx;if(seen.has(k))continue;seen.add(k);q.push([nx,ny,d+1]);}}
    return hits.slice(0,4);
  },{x:s.x,y:s.y});
  if(far.length){
    const tgt=far[0];const pt=proj(s,tgt.x,tgt.y);
    const t0=Date.now();
    await p.mouse.click(pt.x,pt.y);
    let firstStep=null;const traj=[];
    for(let i=0;i<40;i++){const c=await snap();if(c.x!==s.x||c.y!==s.y){if(!firstStep)firstStep=Date.now()-t0;traj.push(`${c.x},${c.y}`);}
      if(c.x===tgt.x&&c.y===tgt.y)break;await p.waitForTimeout(100);}
    const end=await idle();
    out.push({k:'单击 6 步目标',v:`${s.x},${s.y} -> ${end.x},${end.y} 期望 ${tgt.x},${tgt.y}；首步延迟 ${firstStep??'—'}ms；轨迹 ${traj.join(' ')}`});
  } else out.push({k:'单击 6 步目标',v:'无可走目标'});

  // --- 2. 拖拽（缓慢、每格 250ms，与人物节拍同步）---
  s=await idle();
  const dirPath=await p.evaluate(async({x,y})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const m=worldMirror.map;const out=[];let cx=x,cy=y;
    for(let i=0;i<5;i++){let ok=null;
      for(const [dx,dy] of [[1,0],[0,1],[1,1],[-1,0],[0,-1]]){
        const nx=cx+dx,ny=cy+dy;if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
        if(m.collision[ny*m.w+nx]!==1)continue;
        if(dx&&dy&&(m.collision[cy*m.w+nx]!==1||m.collision[ny*m.w+cx]!==1))continue;
        ok={x:nx,y:ny};break;}
      if(!ok)break;out.push(ok);cx=ok.x;cy=ok.y;}
    return out;
  },{x:s.x,y:s.y});
  if(dirPath.length>=3){
    const a=proj(s,dirPath[0].x,dirPath[0].y);
    await p.mouse.move(a.x,a.y);await p.mouse.down();
    for(const q of dirPath.slice(0,4)){const c=await snap();const pt=proj(c,q.x,q.y);
      await p.mouse.move(pt.x,pt.y,{steps:2});await p.waitForTimeout(250);}
    await p.mouse.up();
    const end=await idle(700);
    out.push({k:'拖拽 4 格',v:`${s.x},${s.y} -> ${end.x},${end.y} 目标 ${dirPath[3].x},${dirPath[3].y}`});
  } else out.push({k:'拖拽 4 格',v:'路径不足'});

  // --- 3. 键盘 ---
  s=await idle();
  await p.locator('canvas').first().click({position:{x:40,y:40}});
  await p.waitForTimeout(500);
  const kbStart=await idle();
  await p.keyboard.down('KeyD');await p.waitForTimeout(900);await p.keyboard.up('KeyD');
  const kbEnd=await idle(600);
  out.push({k:'键盘 D',v:`${kbStart.x},${kbStart.y} -> ${kbEnd.x},${kbEnd.y}`});

  // --- 4. Escape 取消 ---
  s=await idle();
  const tgt4=await p.evaluate(async({x,y})=>{
    const {worldMirror}=await import('/src/game/runtime.ts');const m=worldMirror.map;
    const q=[[x,y,0]];const seen=new Set([y*m.w+x]);
    while(q.length){const [cx,cy,d]=q.shift();if(d===8)return{x:cx,y:cy};
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]){
        const nx=cx+dx,ny=cy+dy;if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
        if(m.collision[ny*m.w+nx]!==1)continue;
        if(dx&&dy&&(m.collision[cy*m.w+nx]!==1||m.collision[ny*m.w+cx]!==1))continue;
        const k=ny*m.w+nx;if(seen.has(k))continue;seen.add(k);q.push([nx,ny,d+1]);}}
    return null;
  },{x:s.x,y:s.y});
  if(tgt4){
    const pt=proj(s,tgt4.x,tgt4.y);await p.mouse.click(pt.x,pt.y);
    await p.waitForTimeout(700);
    await p.keyboard.press('Escape');
    const stop=await idle(600);
    await p.waitForTimeout(1200);
    const later=await snap();
    out.push({k:'Escape 取消',v:`目标 ${tgt4.x},${tgt4.y}；Esc 时 ${stop.x},${stop.y}；1.2s 后 ${later.x},${later.y}（应与 Esc 时相同）`});
  } else out.push({k:'Escape 取消',v:'无 8 步目标'});

  out.push({k:'页面异常',v:JSON.stringify(errs)});
  for(const r of out) console.log(`${r.k} :: ${r.v}`);
  fs.writeFileSync(OUT+'move2.json',JSON.stringify(out,null,2));
  await b.close();
})();
