'use strict';
(function(root){
const messages={401:'Votre session a expiré. Reconnectez-vous.',403:'Vous ne disposez pas des droits nécessaires.',404:'Cette ressource est introuvable ou inaccessible.',409:'Le dossier a changé. Rechargez-le avant de réessayer.',413:'Le fichier ou le dossier dépasse la taille autorisée.',422:'Certains éléments doivent être corrigés.',428:'La version du dossier est requise.',429:'Le service est occupé. Réessayez dans un instant.',503:'Le service est momentanément indisponible.'};
class CreditApiError extends Error{constructor(status,message,requestId=null){super(message);this.name='CreditApiError';this.status=status;this.requestId=requestId}}
class CreditApi{
 constructor({baseUrl,fetchImpl=(...args)=>fetch(...args),tokenProvider=()=>null,csrfProvider=()=>null,requireCsrf=false,timeoutMs=20000,onUnauthorized=()=>{}}){const u=new URL(baseUrl);if(u.protocol!=='https:'&&!(u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)))throw new Error('HTTPS requis.');if(u.username||u.password||u.search||u.hash)throw new Error('Adresse de service invalide.');this.base=u.href.replace(/\/$/,'');this.fetch=fetchImpl;this.tokenProvider=tokenProvider;this.csrfProvider=csrfProvider;this.requireCsrf=requireCsrf;this.timeoutMs=timeoutMs;this.onUnauthorized=onUnauthorized}
 async request(path,{method='GET',body,version,key,binary=false,responseType,signal,timeoutMs=this.timeoutMs}={}){
  if(!path.startsWith('/')||path.startsWith('//')||path.includes('\\'))throw new CreditApiError(0,'Chemin de requête invalide.');
  const headers={Accept:'application/json'};const token=await this.tokenProvider();if(token)headers.Authorization='Bearer '+token;
  if(!['GET','HEAD','OPTIONS'].includes(method)){const csrf=await this.csrfProvider();if(this.requireCsrf&&!csrf)throw new CreditApiError(403,'La protection de votre session doit être actualisée.');if(csrf)headers['X-CSRF-Token']=csrf}
  if(version!==undefined)headers['If-Match']=String(version);if(key)headers['Idempotency-Key']=key;
  if(body!==undefined&&!binary)headers['Content-Type']='application/json';if(binary&&body?.type)headers['Content-Type']=body.type;
  const controller=new AbortController();const abort=()=>controller.abort();if(signal?.aborted)controller.abort();else signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{const response=await this.fetch(this.base+path,{method,headers,body:body!==undefined?(binary?body:JSON.stringify(body)):undefined,signal:controller.signal,credentials:'same-origin',redirect:'error',cache:'no-store'});const requestId=response.headers.get('x-request-id');if(response.ok&&responseType==='blob')return response.blob();if(response.ok&&responseType==='text')return response.text();let data=null;
   if(response.status!==204){const raw=await response.text();if(raw){try{data=JSON.parse(raw)}catch{if(response.ok)throw new CreditApiError(502,'La réponse du service est invalide.',requestId)}}}
   if(response.status===401)this.onUnauthorized();if(!response.ok)throw new CreditApiError(response.status,messages[response.status]||'La requête n’a pas abouti.',requestId);return data;
  }catch(error){if(error instanceof CreditApiError)throw error;if(controller.signal.aborted)throw new CreditApiError(408,'La requête a été interrompue ou a dépassé le délai. Vérifiez son état avant de la relancer.');throw new CreditApiError(0,'Connexion interrompue. Vérifiez l’état de votre dossier avant de réessayer.');}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
 }
 casePath(core,id=''){if(!['individuals','businesses'].includes(core))throw new Error('Noyau invalide.');return '/'+core+(id?'/'+encodeURIComponent(id):'')}
 createCase(core,payload){return this.request(this.casePath(core),{method:'POST',body:payload})}
 readCase(core,id){return this.request(this.casePath(core,id))}
 updateCase(core,id,payload,version){if(version===undefined)throw new Error('Version du dossier requise.');return this.request(this.casePath(core,id),{method:'PUT',body:payload,version})}
 policies(){return this.request('/documents/policies')}
 createSubmission(core,id,payload,key){return this.request(this.casePath(core,id)+'/submissions',{method:'POST',body:payload,key})}
 submission(core,id,sub){return this.request(this.casePath(core,id)+'/submissions/'+encodeURIComponent(sub))}
 upload(core,id,sub,file,key,version){return this.request(this.casePath(core,id)+'/submissions/'+encodeURIComponent(sub)+'/sources',{method:'POST',body:file,binary:true,key,version,timeoutMs:120000})}
 editPages(core,id,sub,pages,revision){return this.request(this.casePath(core,id)+'/submissions/'+encodeURIComponent(sub)+'/pages',{method:'PUT',body:{pages,expected_revision:revision}})}
 confirm(core,id,sub,version){return this.request(this.casePath(core,id)+'/submissions/'+encodeURIComponent(sub)+'/confirm',{method:'POST',version})}
 process(core,id,sub){return this.request(this.casePath(core,id)+'/submissions/'+encodeURIComponent(sub)+'/process',{method:'POST',timeoutMs:120000})}
 review(core,id,sub,run,decisions,revision){return this.request(this.casePath(core,id)+'/submissions/'+encodeURIComponent(sub)+'/runs/'+encodeURIComponent(run)+'/reviews',{method:'POST',body:{decisions,expected_review_revision:revision}})}
 assess(core,id,options,key){return this.request(this.casePath(core,id)+'/assessments',{method:'POST',body:options,key})}
 assessment(id){return this.request('/assessments/'+encodeURIComponent(id))}
 simulate(id,specification){return this.request('/assessments/'+encodeURIComponent(id)+'/simulations',{method:'POST',body:{specification}})}
 print(core,id,options,key){return this.request(this.casePath(core,id)+'/print/editions',{method:'POST',body:options,key})}
}
root.CreditApi=CreditApi;root.CreditApiError=CreditApiError;
})(typeof window==='undefined'?globalThis:window);
