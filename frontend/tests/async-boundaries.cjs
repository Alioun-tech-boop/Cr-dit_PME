/* Une réponse tardive ne doit pas réaffecter un autre dossier ou une nouvelle session. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let active={core:'individuals',remote:{id:'a',version:1},analysisKey:'stable-key'};
const context={window:{CreditJourney:{getDraft:()=>active},CreditModel:{buildPayload:()=>({})}},crypto:require('node:crypto').webcrypto};
vm.runInNewContext(fs.readFileSync('dist/backend-services.js','utf8'),context);
function setup(){let resolve;const pending=new Promise(r=>resolve=r);const api={casePath:(core,id)=>'/'+core+'/'+id,request:()=>pending,assess:()=>pending,simulate:()=>pending};const service={ready:true,publishedReport:null,assessmentId:'assessment-a'};context.window.configureCreditBackend(service,api,{role:'analyst',id:'actor'});service.saveCase=async()=>({});service.saveDraft=async()=>({});return {api,service,resolve}}
(async()=>{
 let s=setup(),task=s.service.analyze(active);await new Promise(r=>setImmediate(r));active={core:'businesses',remote:{id:'b',version:1}};s.resolve({id:'assessment-a',result:{source:'case-a'}});await task;assert.equal(s.service.publishedReport,null);
 s=setup();task=s.service.analyze(active);await new Promise(r=>setImmediate(r));s.service.ready=false;s.service.api=null;s.resolve({id:'assessment-b',result:{source:'old-session'}});await task;assert.equal(s.service.publishedReport,null);
 s=setup();task=s.service.simulate();s.service.assessmentId='assessment-b';s.resolve({id:'simulation-a',result:{source:'case-a'}});await task;assert.equal(s.service.publishedReport,null);assert.equal(s.service.assessmentId,'assessment-b');
 console.log('3 contrôles de frontières asynchrones réussis.');
})().catch(e=>{console.error(e);process.exitCode=1});
