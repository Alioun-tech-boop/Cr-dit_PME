'use strict';
(function(root){
root.submitCreditDraft=async function(api,draft,payload){

   if(draft.remote?.uncertain)throw new Error('Un envoi précédent doit être rapproché avec le service avant toute nouvelle tentative.');
   let saved;try{if(draft.remote?.id)saved=await api.updateCase(draft.core,draft.remote.id,payload,draft.remote.version);else saved=await api.createCase(draft.core,payload)}catch(e){if([0,408,502].includes(e.status))draft.remote={...draft.remote,uncertain:true};throw e}
   if(!saved?.id||saved.version===undefined){draft.remote={...draft.remote,...(saved?.id?{id:saved.id}:{}),uncertain:true};throw new Error('L’enregistrement du dossier n’a pas été confirmé par le service.');}draft.remote={id:saved.id,version:saved.version};
   for(const document of draft.documents){if(document.remote?.confirmed)continue;if(document.remote?.uncertain)throw new Error('Une pièce nécessite une vérification de l’envoi précédent.');try{
    let submission=document.remote?.id?await api.submission(draft.core,saved.id,document.remote.id):await api.createSubmission(draft.core,saved.id,{document_type:document.type,period:document.period+'-01',role:document.role,visibility:'applicant'});document.remote={...document.remote,id:submission.id};
    for(const page of document.pages){if(page.serverPages)continue;const before=new Set(submission.pages.map(p=>p.id));submission=await api.upload(draft.core,saved.id,submission.id,page.file);page.serverPages=submission.pages.filter(p=>!before.has(p.id));if(!page.serverPages.length)throw new Error('La réception d’une page n’a pas été confirmée.')}
    const pages=document.pages.flatMap(p=>p.serverPages.map(server=>({id:server.id,rotation:p.mime==='application/pdf'?server.rotation:(server.rotation+p.rotation)%360,crop:p.mime==='application/pdf'?server.crop:p.crop})));submission=await api.editPages(draft.core,saved.id,submission.id,pages,submission.revision);submission=await api.confirm(draft.core,saved.id,submission.id);if(submission.deposit_status!=='confirmed')throw new Error('La confirmation documentaire nécessite une vérification.');document.remote.confirmed=true;
   }catch(e){if(e.status===undefined||[0,408,502].includes(e.status))document.remote={...document.remote,uncertain:true};throw e}}
   return saved;

};
})(typeof window==='undefined'?globalThis:window);
