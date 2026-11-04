const fs=require('node:fs'),path=require('node:path');
const root='C:/Users/zx198/AppData/Local/ms-playwright';
const lib=fs.readdirSync(path.join(root,'.links')).map(n=>fs.readFileSync(path.join(root,'.links',n),'utf8').trim())
  .find(d=>fs.existsSync(path.join(d,'package.json'))&&require(d).chromium);
if(!lib) throw new Error('no linked playwright');
const pw=require(lib);
const exe=pw.chromium.executablePath();
if(!path.resolve(exe).toLowerCase().startsWith(path.resolve(root).toLowerCase()+path.sep))
  throw new Error('browser outside ms-playwright: '+exe);
module.exports={pw,exe,OUT:'C:/tmp/p7accept-20261104/'};
