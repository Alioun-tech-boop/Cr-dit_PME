import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root=process.cwd(),dist=path.join(root,'dist');
const sheets=['style.css','premium.css','journey.css','production.css'];
const css=sheets.map(name=>`/* ${name} */\n`+fs.readFileSync(path.join(root,'src/styles',name),'utf8')).join('\n');
fs.writeFileSync(path.join(dist,'app.css'),css);
const digest=name=>crypto.createHash('sha256').update(fs.readFileSync(path.join(dist,name))).digest('hex').slice(0,12);
for(const [name,stylesheet] of [['platform.html','app.css'],['index.html','public.css'],['login.html','public.css'],['activate-account.html','public.css'],['verify-bank-agreement.html','public.css']]){
let html=fs.readFileSync(path.join(dist,name),'utf8');
html=html.replace(/<link rel="stylesheet" href="(?:style|premium|journey|production|app|public)\.css(?:\?[^\"]*)?">/g,'');
html=html.replace('</title>','</title>\n<link rel="stylesheet" href="'+stylesheet+'?v='+digest(stylesheet)+'">');
html=html.replace(/(<script src=")([a-z-]+\.js)(?:\?[^\"]*)?(" defer><\/script>)/g,(_,start,file,end)=>start+file+'?v='+digest(file)+end);
fs.writeFileSync(path.join(dist,name),html.replace(/\n{3,}/g,'\n\n'));
}
const files=fs.readdirSync(dist).filter(f=>/\.(js|css|html)$/.test(f));
fs.mkdirSync(path.join(root,'tests/output'),{recursive:true});
const manifest=Object.fromEntries(files.map(name=>[name,digest(name)]));
fs.writeFileSync(path.join(root,'tests/output/build-manifest.json'),JSON.stringify(manifest,null,2));
console.log(`Frontend assemblé : ${sheets.length} feuilles de style, ${files.filter(f=>f.endsWith('.js')).length} scripts locaux avec versions de cache.`);
