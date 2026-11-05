import fs from 'node:fs';import {spawnSync} from 'node:child_process';
const commands=[['scripts/build-frontend.mjs'],...fs.readdirSync('dist').filter(n=>n.endsWith('.js')).map(n=>['--check','dist/'+n]),['tests/journey-contracts.cjs'],['tests/production.cjs'],['tests/async-boundaries.cjs']];
for(const args of commands){const result=spawnSync(process.execPath,args,{stdio:'inherit'});if(result.status!==0)process.exit(result.status||1)}
console.log('Vérifications frontend terminées.');
