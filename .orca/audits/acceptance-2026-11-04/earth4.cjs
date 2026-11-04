const {pw,exe,OUT}=require('./lib.cjs');
const ZOOM=3.5,TW=32,TH=16,HH=16;
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  const errs=[];p.on('pageerror',e=>errs.push(String(e)));
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.waitForTimeout(1800);
  const snap=()=>p.evaluate(async()=>{const {worldMirror}=await import('/src/game/runtime.ts');const {useUiStore}=await import('/src/store/uiStore.ts');const a=worldMirror.actors.get(worldMirror.protagonist??'');const r=document.querySelector('canvas').getBoundingClientRect();return{x:a.x,y:a.y,cx:r.left+r.width/2,cy:r.top+r.height/2,inv:useUiStore.getState().voxelInventory,err:useUiStore.getState().voxelError};});
  const proj=(s,x,y,h=1)=>({x:s.cx+((x-s.x)-(y-s.y))*(TW/2)*ZOOM,y:s.cy+((x-s.x)+(y-s.y))*(TH/2)*ZOOM-(h-1)*HH*ZOOM});

  // 枚举：可达格 4-邻中「点顶面中心 = 自己」的土坎，取最近
  const plan=await p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const iso=await import('/src/game/render/iso.ts');
    const pick=await import('/src/game/render/voxel-picking.ts');
    const m=worldMirror.map,a=worldMirror.actors.get(worldMirror.protagonist??'');
    const heightAt=iso.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    const bounds=iso.screenBounds(m.w,m.h);
    // 可达集 + 距离
    const dist=new Int32Array(m.w*m.h).fill(-1);const q=[[a.x,a.y]];dist[a.y*m.w+a.x]=0;
    while(q.length){const [cx,cy]=q.shift();const d=dist[cy*m.w+cx];
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]){
        const nx=cx+dx,ny=cy+dy;if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
        if(m.collision[ny*m.w+nx]!==1)continue;
        if(dx&&dy&&(m.collision[cy*m.w+nx]!==1||m.collision[ny*m.w+cx]!==1))continue;
        const k=ny*m.w+nx;if(dist[k]>=0)continue;dist[k]=d+1;q.push([nx,ny]);}}
    let best=null;
    for(let i=0;i<m.w*m.h;i++){
      if(dist[i]<0)continue;
      const cx=i%m.w,cy=Math.floor(i/m.w);
      for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
        const bx=cx+dx,by=cy+dy;if(bx<0||by<0||bx>=m.w||by>=m.h)continue;
        if(m.collision[by*m.w+bx]!==0||heightAt(bx,by)!==1)continue;
        const t=iso.isoProject(bx,by,1,bounds);
        const v=pick.pickVoxel(t.sx,t.sy,m.w,m.h,heightAt);
        if(!(v&&v.x===bx&&v.y===by))continue;
        if(!best||dist[i]<best.d)best={d:dist[i],stand:{x:cx,y:cy},bank:{x:bx,y:by}};
      }
    }
    return best;
  });
  console.log('plan',JSON.stringify(plan));
  if(!plan){await b.close();return;}

  // 分步走：每次用当前相机投影下一格，走到位再下一步
  let s=await snap();
  const steps=[];
  let guard=0;
  while((s.x!==plan.stand.x||s.y!==plan.stand.y)&&guard++<200){
    const next=await p.evaluate(async({tx,ty})=>{
      const {worldMirror}=await import('/src/game/runtime.ts');
      const m=worldMirror.map,a=worldMirror.actors.get(worldMirror.protagonist??'');
      // BFS 从当前到目标，取第一步
      const prev=new Map();const q=[[a.x,a.y]];const seen=new Set([a.y*m.w+a.x]);
      let found=false;
      while(q.length&&!found){const [cx,cy]=q.shift();
        if(cx===tx&&cy===ty){found=true;break;}
        for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]]){
          const nx=cx+dx,ny=cy+dy;if(nx<0||ny<0||nx>=m.w||ny>=m.h)continue;
          if(m.collision[ny*m.w+nx]!==1)continue;
          if(dx&&dy&&(m.collision[cy*m.w+nx]!==1||m.collision[ny*m.w+cx]!==1))continue;
          const k=ny*m.w+nx;if(seen.has(k))continue;seen.add(k);prev.set(k,{x:cx,y:cy});q.push([nx,ny]);}}
      if(!found)return null;
      let cur={x:tx,y:ty},first=null;
      while(true){const pr=prev.get(cur.y*m.w+cur.x);if(!pr)break;first=cur;cur=pr;}
      return first;
    },{tx:plan.stand.x,ty:plan.stand.y});
    if(!next){console.log('no path');break;}
    const pt=proj(s,next.x,next.y);
    await p.mouse.click(pt.x,pt.y);
    let moved=false;
    for(let i=0;i<30;i++){const c=await snap();if(c.x===next.x&&c.y===next.y){moved=true;break;}await p.waitForTimeout(120);}
    s=await snap();steps.push(`${s.x},${s.y}`);
    if(!moved){console.log('stuck at',s.x,s.y,'err',s.err);break;}
  }
  s=await snap();
  console.log('arrived',s.x,s.y,'target',plan.stand.x,plan.stand.y,'steps',steps.length);
  const bp=proj(s,plan.bank.x,plan.bank.y,1);
  const before=JSON.stringify(s.inv);
  await p.mouse.move(bp.x,bp.y);await p.mouse.down();await p.waitForTimeout(1300);await p.mouse.up();
  await p.waitForTimeout(2500);
  s=await snap();
  const hud=await p.evaluate(()=>{const el=document.querySelector('[aria-label="行囊"]');return el?el.innerText.replace(/\n/g,' | '):null;});
  console.log('earth dig: before',before,'→ after',JSON.stringify(s.inv),'HUD',JSON.stringify(hud),'err',JSON.stringify(s.err));
  await p.screenshot({path:OUT+'P-earth-ok.png'});
  console.log('errors',JSON.stringify(errs));
  await b.close();
})();
