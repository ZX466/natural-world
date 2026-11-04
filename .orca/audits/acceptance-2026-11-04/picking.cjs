const {pw,exe,OUT}=require('./lib.cjs');
(async()=>{
  const b=await pw.chromium.launch({headless:true,executablePath:exe});
  const ctx=await b.newContext({viewport:{width:1440,height:900},locale:'zh-CN'});
  const p=await ctx.newPage();
  await p.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
  await p.waitForFunction(()=>{const d=document.querySelector('.od-status');return d&&d.getAttribute('aria-label')==='连接正常';},{timeout:20000});
  await p.waitForTimeout(1500);
  const r=await p.evaluate(async()=>{
    const {worldMirror}=await import('/src/game/runtime.ts');
    const iso=await import('/src/game/render/iso.ts');
    const pick=await import('/src/game/render/voxel-picking.ts');
    const m=worldMirror.map;
    const heightAt=iso.createHeightLookup(await (await fetch('/assets/tilesets/linhe-height.json')).json());
    const bounds=iso.screenBounds(m.w,m.h);
    const walkable=(x,y)=>m.collision[y*m.w+x]===1;
    // A. 可走格：点自己顶面中心 → pickGround 是否命中自己
    let okG=0,badG=0,badGEx=[];
    // B. 土坎：点自己顶面中心 → pickVoxel 是否命中自己
    let okB=0,badB=0,badBEx=[];
    // C. h>=2 阻挡块：点自己顶面中心 → pickVoxel 是否命中自己
    let okH=0,badH=0,badHEx=[];
    for(let y=0;y<m.h;y++)for(let x=0;x<m.w;x++){
      const i=y*m.w+x,hh=heightAt(x,y);
      if(m.collision[i]===1){
        const t=iso.isoProject(x,y,1,bounds);
        const g=pick.pickGround(t.sx,t.sy,m.w,m.h,heightAt,walkable);
        if(g&&g.x===x&&g.y===y)okG++;else{badG++;if(badGEx.length<5)badGEx.push({x,y,g});}
      } else if(hh===1){
        const t=iso.isoProject(x,y,1,bounds);
        const v=pick.pickVoxel(t.sx,t.sy,m.w,m.h,heightAt);
        if(v&&v.x===x&&v.y===y)okB++;else{badB++;if(badBEx.length<5)badBEx.push({x,y,v});}
      } else if(hh>=2){
        const t=iso.isoProject(x,y,hh,bounds);
        const v=pick.pickVoxel(t.sx,t.sy,m.w,m.h,heightAt);
        if(v&&v.x===x&&v.y===y)okH++;else{badH++;if(badHEx.length<5)badHEx.push({x,y,hh,v});}
      }
    }
    return {walk:{ok:okG,bad:badG,ex:badGEx},bank:{ok:okB,bad:badB,ex:badBEx},high:{ok:okH,bad:badH,ex:badHEx}};
  });
  console.log(JSON.stringify(r,null,1));
  await b.close();
})();
