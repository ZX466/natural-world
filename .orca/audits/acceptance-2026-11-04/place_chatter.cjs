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

  // 放：右键点一个 4 格内、可走（collision 1）的格 → 消耗对应材料并抬高
  let s=await snap();
  const target=await p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const iso=await import('/src/game/render/iso.ts');
    const pick=await import('/src/game/render/voxel-picking.ts');
    const m=worldMirror.map,a=worldMirror.actors.get(worldMirror.protagonist??'');
    const heightAt=iso.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    const bounds=iso.screenBounds(m.w,m.h);
    for(let dy=-3;dy<=3;dy++)for(let dx=-3;dx<=3;dx++){
      const x=a.x+dx,y=a.y+dy;if(x<0||y<0||x>=m.w||y>=m.h)continue;
      if(Math.abs(dx)+Math.abs(dy)>3)continue;
      if(m.collision[y*m.w+x]!==1)continue;
      const t=iso.isoProject(x,y,1,bounds);
      const v=pick.pickVoxel(t.sx,t.sy,m.w,m.h,heightAt);
      if(!v||v.x!==x||v.y!==y)continue; // 需点到自己，否则右键会放错格
      return {x,y};
    }
    return null;
  });
  console.log('place target',JSON.stringify(target),'inv before',JSON.stringify(s.inv));
  if(target){
    const pt=proj(s,target.x,target.y,1);
    await p.mouse.click(pt.x,pt.y,{button:'right'});
    await p.waitForTimeout(2500);
    s=await snap();
    const edits=await p.evaluate(async()=>{const {worldMirror}=await import('/src/game/runtime.ts');return [...worldMirror.voxelEdits.entries()].map(([k,v])=>({k,action:v.action,height:v.height,gid:v.gid}));});
    console.log('after place inv',JSON.stringify(s.inv),'err',JSON.stringify(s.err),'edits',JSON.stringify(edits.slice(-3)));
  }

  // 心声/街巷采样 90 秒
  const sample=await p.evaluate(()=>{const {useUiStore}=window.__p7store||{};return null;}).catch(()=>null);
  const rows=[];
  for(let i=0;i<45;i++){
    const t=await p.evaluate(async()=>{
      const {useUiStore}=await import('/src/store/uiStore.ts');
      const st=useUiStore.getState();
      return {mono:st.monologues.map(m=>m.content),chatter:st.chatter.map(c=>c.content),clock:st.gameClock};
    });
    rows.push(t);
    await p.waitForTimeout(2000);
  }
  const allChatter=[...new Set(rows.flatMap(r=>r.chatter))];
  const allMono=[...new Set(rows.flatMap(r=>r.mono))];
  const retells=allChatter.filter(c=>c.startsWith('听')&&c.includes('说，'));
  const selfNameRetell=retells.filter(c=>{const m=/^听([^说，]+)说，(.+)$/.exec(c);return m&&m[2].startsWith(m[1]);});
  console.log('chatter 去重条数',allChatter.length,'其中「听X说」转述',retells.length,'转述里重复说话人名',selfNameRetell.length);
  console.log('样本转述:',JSON.stringify(retells.slice(0,8)));
  console.log('重复说话人名样本:',JSON.stringify(selfNameRetell.slice(0,5)));
  console.log('心声去重条数',allMono.length,'样本',JSON.stringify(allMono.slice(0,6)));
  const finalClock=rows[rows.length-1].clock;
  console.log('采样期间时钟',JSON.stringify(rows[0].clock),'→',JSON.stringify(finalClock));
  await p.screenshot({path:OUT+'Q-chatter.png'});
  console.log('errors',JSON.stringify(errs));
  await b.close();
})();
