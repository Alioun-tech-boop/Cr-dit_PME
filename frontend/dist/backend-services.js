'use strict';
/* Adaptation HTTP uniquement. Les calculs et autorisations restent sur le serveur. */
window.configureCreditBackend=function(services,api,user){
 let reportRequest=0;const journey=()=>window.CreditJourney;const staff=['analyst','institution_manager','administrator'].includes(user.role);
 services.staff=staff;services.user=user;
 const path=d=>api.casePath(d.core,d.remote.id);
 const copy=d=>JSON.parse(JSON.stringify(d,(k,v)=>['file','original','baseline','report','remoteDraft'].includes(k)?undefined:k==='url'&&String(v).startsWith('blob:')?undefined:v));
 const key=(obj,name)=>obj[name]||(obj[name]=crypto.randomUUID());
 function accepted(d,result){d.remoteDraft={id:result.id,version:result.version};return result}
 services.saveDraft=async d=>{
  if(!services.ready)throw new Error('Connectez-vous avant de sauvegarder.');
  const operationKey=key(d,'saveKey');const body={kind:d.core,draft:copy(d),case_id:d.remote?.id??null,case_version:d.remote?.version??null};
  const result=d.remoteDraft?await api.request('/journeys/'+d.remoteDraft.id,{method:'PUT',body,version:d.remoteDraft.version}):await api.request('/journeys',{method:'POST',body,key:operationKey});
  return accepted(d,result);
 };
 services.saveCase=async(d,payload)=>{
  await services.saveDraft(d);
  try{const r=await api.request('/journeys/'+d.remoteDraft.id+'/case',{method:'POST',body:{payload,case_version:d.remote?.version??null},version:d.remoteDraft.version});d.remote={id:r.id,version:r.version};d.remoteDraft.version=r.draft_version;return r}
  catch(e){if([0,408,502].includes(e.status)){const state=await api.request('/journeys/'+d.remoteDraft.id).catch(()=>null);if(state?.case_id){const found=await api.readCase(d.core,state.case_id);if(JSON.stringify(found.data)===JSON.stringify(payload)){accepted(d,state);d.remote={id:found.id,version:found.version};return found}}d.remote={...d.remote,uncertain:true};await services.saveDraft(d).catch(()=>{});}throw e}
 };
 services.stageDocuments=async d=>{
  if(!services.ready)throw new Error('Connectez-vous pour déposer les fichiers.');
  if(window.CreditModel.validate(d).length)throw new Error('Complétez les champs financiers avant le dépôt. Les fichiers sont encore uniquement sur cette page.');
  await services.saveCase(d,window.CreditModel.buildPayload(d));
  for(const doc of d.documents){
   if(doc.remote?.confirmed)continue;
   key(doc,'operationKey');for(const page of doc.pages){key(page,'uploadKey');if(page.file&&!page.uploadSha)page.uploadSha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',await page.file.arrayBuffer()))].map(v=>v.toString(16).padStart(2,'0')).join('')}await services.saveDraft(d);
   let sub=doc.remote?.id?await api.submission(d.core,d.remote.id,doc.remote.id):await api.createSubmission(d.core,d.remote.id,{document_type:doc.type,period:doc.period+'-01',role:doc.role,visibility:'applicant'},doc.operationKey);
   if(doc.remote?.id&&doc.remote.revision!==sub.revision&&!doc.pages.some(p=>sub._upload_revisions?.[p.uploadKey]===sub.revision))throw new Error('La pièce a changé. Rechargez ses pages avant de poursuivre.');
   doc.remote={id:sub.id,revision:sub.revision,confirmed:sub.deposit_status==='confirmed'};
   for(const page of [...doc.pages]){
    if(page.serverId)continue;
    const received=page.uploadSha?sub.security_checks?.find(s=>s.sha256===page.uploadSha):null;if(received){const added=sub.pages.filter(p=>p.source_id===received.source_id);doc.pages.splice(doc.pages.indexOf(page),1,...added.map(p=>({serverId:p.id,name:page.name,mime:'image/png',size:page.size,rotation:page.rotation||p.rotation,crop:page.crop,sourceRotation:p.rotation,serverCrop:p.crop,url:api.base+path(d)+'/submissions/'+sub.id+'/pages/'+p.id+'/image?original=true'})));continue}if(!page.file)throw new Error('Ce fichier local n’a pas été reçu. Sélectionnez-le à nouveau ; les fichiers déjà déposés restent conservés.');
    const before=new Set(sub.pages.map(p=>p.id));
    sub=await api.upload(d.core,d.remote.id,sub.id,page.file,page.uploadKey,sub.revision);
    // L'empreinte et la clé d'envoi identifient aussi une réponse précédemment perdue.
    let added=sub.pages.filter(p=>!before.has(p.id));
    if(!added.length){const bytes=await page.file.arrayBuffer();const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');const source=sub.security_checks?.find?.(s=>s.sha256===sha);added=sub.pages.filter(p=>p.sha256===sha||p.source_id===source?.source_id)}
    if(!added.length)throw new Error('Réception incertaine : consultez la pièce avant un nouvel envoi.');
    const i=doc.pages.indexOf(page);doc.pages.splice(i,1,...added.map(p=>({serverId:p.id,name:page.name,mime:'image/png',size:page.size,rotation:page.rotation||p.rotation,crop:page.crop,sourceRotation:p.rotation,serverCrop:p.crop,url:api.base+path(d)+'/submissions/'+sub.id+'/pages/'+p.id+'/image?original=true'})));
    doc.remote.revision=sub.revision;await services.saveDraft(d);
   }
   sub=await api.submission(d.core,d.remote.id,sub.id);
   if(doc.remote.revision!==sub.revision)throw new Error('La pièce a changé. Actualisez ses pages avant de modifier l’ordre ou le cadrage.');
   if(sub.deposit_status==='draft'){sub=await api.editPages(d.core,d.remote.id,sub.id,doc.pages.map(p=>({id:p.serverId,rotation:p.rotation,crop:p.crop})),sub.revision)}
   doc.remote.revision=sub.revision;doc.status=sub;await services.saveDraft(d);
  }
 };
 services.submitDraft=async(d,payload)=>{
  await services.stageDocuments(d);
  for(const doc of d.documents){if(doc.remote.confirmed)continue;const result=await api.confirm(d.core,d.remote.id,doc.remote.id,doc.remote.revision);doc.status=result;doc.remote.confirmed=result.deposit_status==='confirmed';if(!doc.remote.confirmed)throw new Error('Confirmation non obtenue. Consultez les contrôles qualité.')}
  d.reviewState='awaiting_review';await services.saveDraft(d);return d.remote;
 };
 services.refreshPolicies=async()=>{const p=await api.policies();journey().setPolicies(p);return p};
 services.loadReport=async d=>{
  const request=++reportRequest;services.publishedReport=null;services.assessmentId=null;services.audience=null;
  if(!d?.remote?.id)return;
  try{const endpoint=window.CREDIT_RUNTIME.publishedAssessmentEndpoint.replace('{core}',d.core).replace('{id}',encodeURIComponent(d.remote.id));const r=await api.request(endpoint);if(request!==reportRequest||services.api!==api||!services.ready)return;services.publishedReport=r.report;services.assessmentId=r.assessment_id;services.audience=r.audience}
  catch(e){if(e.status!==404)throw e}
 };
 services.loadAll=async()=>{
  if(['bank_agent','bank_manager'].includes(user.role)){journey().clear();if(!location.hash.startsWith('#bank-')&&!['#profile','#settings'].includes(location.hash))location.hash='bank-inbox';return []}
  const [drafts,individuals,businesses]=await Promise.all([api.request('/journeys'),api.request('/individuals'),api.request('/businesses'),services.refreshPolicies()]);
  const rows=[];const attached=new Set();
  for(const item of drafts){let d=item.draft;d.remoteDraft={id:item.id,version:item.version};d.sourceDemo=false;d.id=item.id;
   if(item.case_id){const c=[...individuals,...businesses].find(c=>c.id===item.case_id);if(!c)continue;const from=window.CreditModel.fromCase(item.kind,c.data);d.original=from.original;d.baseline=from.baseline;d.remote={id:c.id,version:item.case_version??c.version};attached.add(c.id)}
   d.documents=d.documents||[];d.actions=d.actions||{};for(const doc of d.documents)for(const p of doc.pages)if(p.serverId&&d.remote?.id)p.url=api.base+path(d)+'/submissions/'+doc.remote.id+'/pages/'+p.serverId+'/image?original=true';rows.push(d);
  }
  for(const c of [...individuals,...businesses])if(!attached.has(c.id)){const d=window.CreditModel.fromCase(c.kind,c.data);d.id=c.id;d.remote={id:c.id,version:c.version};rows.push(d)}
  for(const d of rows)if(d.remote?.id){const subs=await api.request(path(d)+'/submissions');d.documents=subs.map(sub=>{const old=d.documents.find(x=>x.remote?.id===sub.id||x.operationKey===sub._operation_key);return {...old,type:sub.document_type,period:sub.period.slice(0,7),role:sub.role,remote:{...old?.remote,id:sub.id,revision:sub.revision,confirmed:sub.deposit_status==='confirmed'},status:sub,pages:sub.pages.map(p=>({serverId:p.id,name:'Page '+p.source_page,mime:'image/png',size:0,rotation:p.rotation,crop:p.crop,url:api.base+path(d)+'/submissions/'+sub.id+'/pages/'+p.id+'/image?original=true'}))}})}
  if(services.api!==api||!services.ready)return [];journey().replaceDrafts(rows);if(rows[0])await services.loadReport(rows[0]);return rows;
 };
 services.readBudget=async d=>{if(!services.ready||!d?.remote?.id)return null;const r=await api.request(path(d)+'/published-assessment');return r.report.budget_chart||null};
 services.openDraft=async d=>{await services.loadReport(d);await services.refreshPolicies();window.renderApp()};
 services.analyze=async d=>{await services.saveCase(d,window.CreditModel.buildPayload(d));const signature=JSON.stringify([d.remote.version,d.validatedSources||[],d.financialV2Options||{}]);if(d.analysisSignature!==signature){d.analysisSignature=signature;d.analysisKey=crypto.randomUUID();await services.saveDraft(d)}const r=await api.request(api.casePath(d.core,d.remote.id)+'/financial-analyses',{method:'POST',body:{...(d.financialV2Options||{}),mode:'real',validated_sources:d.validatedSources||[]},key:key(d,'analysisKey'),version:d.remote.version,timeoutMs:120000});if(journey().getDraft()!==d||services.api!==api||!services.ready)return r;services.publishedReport=r.result;services.assessmentId=r.id;services.audience='analyst';return r};
 services.publish=async flags=>api.request('/assessments/'+services.assessmentId+'/print-publication',{method:'POST',body:flags});
 services.simulate=async()=>{const originalId=services.assessmentId;const originalDraft=journey().getDraft();const isV2=services.publishedReport?.engine_version==='financial_analysis_v2';const r=isV2?await api.request('/financial-analyses/'+encodeURIComponent(originalId)+'/simulations',{method:'POST',body:{id:'income-drop-20',name:'Baisse hypothétique de 20 %',revenue_drop:'0.20',rationale:'Simulation illustrative demandée par l’utilisateur, sans valeur de norme'},timeoutMs:120000}):await api.simulate(originalId,{kind:'stress',scenario:{revenue_drop:'0.20'}});if(services.assessmentId!==originalId||journey().getDraft()!==originalDraft||services.api!==api||!services.ready)return r;services.publishedReport={...r.result,_stress:true};services.assessmentId=r.id;return r};
 services.print=async(d,template='analysis_report')=>{
  if(!d?.remote?.id)throw new Error('Enregistrez le dossier avant de générer un document.');
  const r=await api.print(d.core,d.remote.id,{template_id:template,audience:staff?'analyst':'applicant',assessment_id:['analysis_report','improvement_plan','analysis_summary','simulation_report'].includes(template)?services.assessmentId:null,language:'fr',generate_now:true},crypto.randomUUID());
  if(services.api!==api||!services.ready)throw new Error('Session modifiée : génération conservée dans son historique autorisé.');if(r.status!=='completed')throw new Error('Génération non terminée : '+r.status);
  const blob=await api.request('/print-editions/'+r.id+'/pdf',{responseType:'blob'});if(services.api!==api||!services.ready)throw new Error('Session modifiée : téléchargement annulé.');const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='credit-pme-'+template+'-'+d.remote.id+'.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);return r;
 };
 services.documentAction=async(d,doc,action)=>{const r=await api.request(path(d)+'/submissions/'+doc.remote.id+'/'+action,{method:'POST',timeoutMs:120000});doc.status=r;return r};
 services.run=async(d,doc)=>api.request(path(d)+'/submissions/'+doc.remote.id+'/runs/'+doc.status.latest_run_id);
 services.review=async(d,doc,decisions,revision)=>api.review(d.core,d.remote.id,doc.remote.id,doc.status.latest_run_id,decisions,revision);
 services.reloadCase=async d=>{if(!d.remote?.id)throw new Error('Ce brouillon n’a pas encore de dossier métier.');const result=await api.readCase(d.core,d.remote.id);const latestDraft=d.remoteDraft?await api.request('/journeys/'+d.remoteDraft.id):null;const fresh=window.CreditModel.fromCase(d.core,result.data);Object.assign(fresh,{id:d.id,remote:{id:result.id,version:result.version},remoteDraft:latestDraft?{id:latestDraft.id,version:latestDraft.version}:undefined,documents:d.documents,actions:d.actions,financialV2Options:d.financialV2Options});await services.saveCase(fresh,window.CreditModel.buildPayload(fresh));journey().replaceDraft(fresh);await services.loadReport(fresh);return fresh};
 services.removeDocument=async(d,doc)=>{if(doc.remote?.id)await api.request(path(d)+'/submissions/'+doc.remote.id+'/withdraw',{method:'POST',version:doc.remote.revision})};
 services.api=api;services.enhanceView=view=>window.enhanceCreditBackend(services,view);
};

/* Commandes dans les panneaux existants ; aucune modification du design. */
window.enhanceCreditBackend=function(services,view){
 if(!services.ready)return;const d=window.CreditJourney.getDraft();if(!d)return;const esc=s=>safe(String(s??''));
 const run=(b,fn)=>async()=>{b.disabled=true;try{await fn();window.renderApp()}catch(e){toast(e.message)}finally{b.disabled=false}};
 const panel=document.createElement('section');panel.className='form-panel';panel.id='server-actions';panel.innerHTML='<span class="mini-kicker">DOSSIER & ACCÈS AUTORISÉS</span><div class="inline-buttons"><button class="outline" id="server-save">Enregistrer le brouillon</button><button class="outline" id="server-refresh">Actualiser les résultats</button><button class="outline" id="server-case-pdf">Dossier récapitulatif PDF</button><button class="outline" id="server-edit">Modifier les champs du dossier</button><button class="outline" id="server-reload-case">Recharger les champs du serveur</button></div>';view.append(panel);
 const bind=(id,fn)=>{const b=panel.querySelector('#'+id);b.onclick=run(b,fn)};
 bind('server-edit',async()=>{d.reviewState='not_submitted';await services.saveDraft(d);location.hash='demande/'+d.step});bind('server-reload-case',async()=>{await services.reloadCase(d);toast('Champs remplacés par la version serveur. Les pièces sont conservées.')});
 bind('server-save',async()=>{await services.saveDraft(d);toast('Brouillon enregistré sur le serveur.')});bind('server-refresh',async()=>{await services.loadReport(d);for(const doc of d.documents)if(doc.remote?.id)doc.status=await services.api.submission(d.core,d.remote.id,doc.remote.id)});bind('server-case-pdf',()=>services.print(d,'complete_file'));
 if(services.staff&&d.remote?.id){const controls=document.createElement('div');controls.className='inline-buttons';controls.innerHTML='<button class="primary" id="server-analyze">Lancer l’analyse réelle</button><button class="outline" id="server-publish">Paramètres de communication</button><button class="outline" id="server-bind-sources">Rattacher des valeurs revues</button>';panel.append(controls);
 bind('server-bind-sources',async()=>{openModal('<h2>Rattachement explicite aux calculs</h2><p>Chaque référence doit viser une revue humaine actuelle du même dossier. Le serveur vérifie la période, la devise, l’unité et le chemin cible. La saisie originale reste conservée.</p><form id="bind-reviewed-form"><label class="field"><span>Liste JSON : review_id, field, target_path, expected_period</span><textarea name="bindings" rows="8" required>'+esc(JSON.stringify(d.validatedSources||[],null,2))+'</textarea></label><button class="primary" type="submit">Confirmer ces rattachements</button><p id="bindings-message" role="status"></p></form>','CHOIX DE L’ANALYSTE');document.querySelector('#bind-reviewed-form').onsubmit=async e=>{e.preventDefault();try{const bindings=JSON.parse(new FormData(e.target).get('bindings'));if(!Array.isArray(bindings))throw new Error('Une liste JSON est requise.');d.validatedSources=bindings;await services.saveDraft(d);document.querySelector('#modal').close();toast('Rattachements enregistrés ; ils seront contrôlés au lancement de l’analyse.')}catch(err){document.querySelector('#bindings-message').textContent=err.message}}});
 bind('server-analyze',async()=>{await services.analyze(d);location.hash='analysis'});
 bind('server-publish',async()=>{if(!services.assessmentId)throw new Error('Chargez une analyse auparavant.');openModal('<h2>Communication au demandeur</h2><p>Sources, scores et observations internes exclus.</p><form id="publication-form"><label class="check-field"><input name="financial_results" type="checkbox"><span>Résultats financiers</span></label><label class="check-field"><input name="suggestions" type="checkbox"><span>Suggestions au demandeur</span></label><label class="field"><span>Justification</span><textarea name="justification" required minlength="5" maxlength="1000"></textarea></label><button class="primary" type="submit">Enregistrer la communication</button></form>','AUTORISATION EXPLICITE');document.querySelector('#publication-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{await services.publish({financial_results:f.has('financial_results'),suggestions:f.has('suggestions'),justification:f.get('justification')});document.querySelector('#modal').close();toast('Communication enregistrée.')}catch(err){toast(err.message)}}});}
 view.querySelectorAll('.uploaded-document').forEach((article,i)=>{const doc=d.documents[i];if(!doc?.remote?.id)return;const box=document.createElement('div');box.className='inline-buttons';box.innerHTML='<button class="outline" data-server-pages>Enregistrer l’ordre et le cadrage</button><button class="outline" data-reload-pages>Recharger les pages du serveur</button>'+(services.staff?'<button class="outline" data-process>Traiter / OCR français</button><button class="outline" data-review>Revoir les transcriptions</button>':'');article.append(box);if(doc.remote.confirmed)article.querySelectorAll('[data-remove-doc],[data-add-pages],[data-remove-page],[data-rotate],[data-crop],[data-move]').forEach(b=>b.disabled=true);for(const [index,p]of (doc.status?.pages||[]).entries()){for(const issue of p.inspection?.quality?.issues||[]){const message=document.createElement('p');message.textContent='Page '+(index+1)+' · '+issue.severity+' : '+issue.message;article.append(message)}}
 const reload=box.querySelector('[data-reload-pages]');reload.onclick=run(reload,async()=>{const sub=await services.api.submission(d.core,d.remote.id,doc.remote.id);doc.status=sub;doc.remote.revision=sub.revision;doc.pages=sub.pages.map(p=>({serverId:p.id,name:'Page '+p.source_page,mime:'image/png',size:0,rotation:p.rotation,crop:p.crop,url:services.api.base+services.api.casePath(d.core,d.remote.id)+'/submissions/'+sub.id+'/pages/'+p.id+'/image?original=true'}));toast('Pages rechargées ; les modifications locales non enregistrées sont remplacées.')});
 const b=box.querySelector('[data-server-pages]');b.disabled=!!doc.remote.confirmed;b.onclick=run(b,()=>services.stageDocuments(d));
 const process=box.querySelector('[data-process]');if(process)process.onclick=run(process,async()=>{await services.documentAction(d,doc,'process');await services.saveDraft(d);toast('Traitement : '+doc.status.processing_status+' · OCR : '+doc.status.ocr_status)});
 const review=box.querySelector('[data-review]');if(review)review.onclick=run(review,async()=>{if(!doc.status?.latest_run_id)throw new Error('Traitez la pièce avant la revue.');const result=await services.run(d,doc);const extraction=result.extraction||result.data?.extraction;if(!extraction)throw new Error('Extraction indisponible.');const candidates=Object.entries(extraction.fields||{}).map(([k,v])=>'<h3>'+esc(k)+'</h3><pre>'+esc(JSON.stringify(v,null,2))+'</pre>').join('');openModal('<h2>Transcriptions et sources</h2><p>La revue ne certifie pas l’authenticité. Aucun candidat n’est envoyé automatiquement aux calculs.</p>'+doc.pages.map(p=>'<img class="local-preview" src="'+esc(p.url)+'" alt="Page source autorisée">').join('')+candidates+'<details><summary>Preuves et tableaux bruts</summary><pre>'+esc(JSON.stringify({evidence:extraction.evidence,tables:extraction.tables},null,2))+'</pre></details><form id="server-review-form"><label class="field"><span>Décisions JSON : champ → value, evidence_ids, reason</span><textarea name="decisions" rows="8" required placeholder="{}"></textarea></label><p id="review-message" role="status"></p><button class="primary" type="submit">Enregistrer la revue humaine</button></form>','REVUE HUMAINE');document.querySelector('#server-review-form').onsubmit=async e=>{e.preventDefault();try{await services.review(d,doc,JSON.parse(new FormData(e.target).get('decisions')),doc.status.review_revision||0);doc.status=await services.api.submission(d.core,d.remote.id,doc.remote.id);await services.saveDraft(d);document.querySelector('#modal').close();toast('Transcription revue, authenticité non certifiée.')}catch(err){document.querySelector('#review-message').textContent=err.message}}});
 });
};
