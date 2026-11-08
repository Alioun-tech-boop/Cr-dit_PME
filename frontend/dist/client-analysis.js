'use strict';
/* Analyse client détaillée : lecture seule de la charge utile publiée par le serveur.
   Aucun calcul financier, score ou recommandation n'est produit dans le navigateur. */
(function(root){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const has=v=>v!==null&&v!==undefined&&v!=='';
 const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
 const nf=new Intl.NumberFormat('fr-FR',{maximumFractionDigits:2});
 const df=new Intl.DateTimeFormat('fr-FR',{dateStyle:'long'});
 const dtf=new Intl.DateTimeFormat('fr-FR',{dateStyle:'long',timeStyle:'short'});
 const DECIMALS=new Intl.NumberFormat('fr-FR',{minimumFractionDigits:0,maximumFractionDigits:2});
 function amount(v){const n=num(v);return n===null?'Non disponible':nf.format(n)+' FCFA'}
 function points(v){const n=num(v);return n===null?'—':DECIMALS.format(n)}
 function percent(v){const n=num(v);return n===null?'Non disponible':nf.format(n*100)+' %'}
 function duration(v){const n=num(v);return n===null?'Non disponible':DECIMALS.format(n)+' mois'}
 function date(v){if(!has(v))return 'Non disponible';const d=new Date(v);return Number.isNaN(d.getTime())?esc(v):df.format(d)}
 function dateTime(v){if(!has(v))return 'Non disponible';const d=new Date(v);return Number.isNaN(d.getTime())?esc(v):dtf.format(d)}
 function shortId(v){return has(v)?esc(String(v).slice(0,8).toUpperCase()):'—'}
 function safeHref(v){return typeof v==='string'&&v.startsWith('/')&&!v.startsWith('//')&&!v.includes('\\')?v:null}
 function list(items,cls=''){const rows=(items||[]).filter(has);return rows.length?'<ul class="ca-list '+cls+'">'+rows.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'<p class="ca-notice">Aucun élément.</p>'}
 const LEVEL={low:['green','Faible'],moderate:['amber','Modéré'],high:['red','Élevé'],critical:['red','Critique'],unknown:['grey','Indéterminé'],incomplete:['amber','Incomplet'],complete:['green','Complet'],required:['amber','Requis'],not_required:['grey','Non requis'],available:['green','Disponible'],not_available:['grey','Non disponible'],computed:['green','Calculé'],needs_explicit_data:['amber','Données à préciser']};
 function badge(value,label){const item=LEVEL[value]||['grey',label||value||'—'];return '<span class="badge '+item[0]+'">'+esc(label||item[1])+'</span>'}
 const OUTCOME_CLASS={favorable:'green',favorable_sous_conditions:'amber',analyse_complementaire_necessaire:'amber',defavorable:'red'};
 const STATE_CLASS={analyse_terminee:'grey',analyse_suspendue:'red',informations_manquantes:'amber',favorable:'green',favorable_sous_conditions:'amber',defavorable:'red'};
 const DIRECTION={up:'En hausse',down:'En baisse',stable:'Stable',unknown:'Indéterminé'};
 const ASSUMPTION_LABELS={revenue_drop:'Baisse des revenus',expense_increase:'Hausse des charges',variable_cost_increase:'Hausse des coûts variables',loss_source:'Perte de source',delay_periods:'Retard d’échéance',additional_instalment:'Échéance supplémentaire',id:'Identifiant',name:'Nom',rationale:'Justification'};
 const PERCENT_CRITERIA=new Set(['debt_service_ratio','min_margin_ratio','income_stability','income_concentration','expense_ratio','net_margin','turnover_growth','debt_burden','customer_concentration']);
 const PERCENT_LABEL=/part|poids|marge nette|croissance|variabilité|taux|écart type|premier client/i;

 function groupValue(item){
  if(!has(item?.value))return 'Non disponible';
  const unit=item.unit||'';
  if(unit==='XOF')return amount(item.value);
  if(unit==='mois')return DECIMALS.format(num(item.value))+' mois';
  if(unit==='jours')return DECIMALS.format(num(item.value))+' j';
  if(unit==='ratio')return PERCENT_LABEL.test(item.label||'')||PERCENT_LABEL.test(item.formula||'')?percent(item.value):points(item.value);
  return esc(item.value)+' '+esc(unit);
 }
 function criterionValue(c){
  if(!has(c?.value))return 'Non disponible';
  const unit=c.unit||'';
  if(unit==='XOF')return amount(c.value);
  if(unit==='mois')return DECIMALS.format(num(c.value))+' mois';
  if(unit==='jours')return DECIMALS.format(num(c.value))+' j';
  if(unit==='ratio')return PERCENT_CRITERIA.has(c.id)?percent(c.value):points(c.value);
  return esc(c.value)+' '+esc(unit);
 }
 function assumptions(value){
  if(!has(value))return '';
  if(typeof value==='string')return '<p class="ca-notice">'+esc(value)+'</p>';
  if(typeof value!=='object')return '<p class="ca-notice">'+esc(value)+'</p>';
  const rows=Object.entries(value).filter(([k,v])=>has(v)&&!['id','name','rationale'].includes(k));
  const title=[value.name,value.rationale].filter(has).map(esc).join(' · ');
  const items=rows.map(([k,v])=>{
   const label=ASSUMPTION_LABELS[k]||k.replaceAll('_',' ');
   const rendered=['revenue_drop','expense_increase','variable_cost_increase'].includes(k)?percent(v):esc(v);
   return '<span class="ca-assumption"><b>'+esc(label)+'</b> '+rendered+'</span>';
  }).join('');
  return (title?'<p class="ca-notice">'+title+'</p>':'')+(items?'<div class="ca-assumptions">'+items+'</div>':'');
 }
 function kpi(label,value,note){return '<div class="ca-kpi"><small>'+esc(label)+'</small><strong>'+value+'</strong>'+(note?'<span>'+note+'</span>':'')+'</div>'}
 function section(kicker,title,body){return '<section class="ca-section"><header><div><span class="mini-kicker">'+esc(kicker)+'</span><h3>'+esc(title)+'</h3></div></header>'+body+'</section>'}

 function ring(score){
  const n=num(score);const safe=n===null?0:Math.max(0,Math.min(100,n));
  return '<div class="ca-ring" style="--ca-score:'+safe+'" role="img" aria-label="Score financier '+(n===null?'indisponible':DECIMALS.format(safe)+' sur 100')+'"><span><strong>'+(n===null?'—':DECIMALS.format(safe))+'</strong><small>/ 100</small></span></div>';
 }

 function summarySection(d){
  const s=d.summary||{},decision=d.decision||{},reliability=d.reliability||{};
  return section('SYNTHÈSE','Ce que dit votre analyse',
   '<div class="ca-kpis">'+
    kpi('Montant demandé',amount(d.dossier?.requested_amount))+
    kpi('Durée demandée',duration(d.dossier?.duration_months))+
    kpi('Capacité mensuelle',amount(s.monthly_capacity))+
    kpi('Marge minimale après crédit',amount(s.minimum_margin))+
    kpi('Recommandation',esc(s.recommendation||decision.label||'Non disponible'))+
    kpi('Statut de la garantie',esc(s.guarantee_status_label||'Non créée'))+
   '</div>'+
   '<div class="ca-summary-grid">'+
    '<div class="ca-summary-card"><span class="mini-kicker">DÉCISION</span><h4>'+esc(decision.label||'Non disponible')+' '+badge(decision.outcome,decision.label)+'</h4><p class="ca-notice">'+esc(decision.notice||'')+'</p></div>'+
    '<div class="ca-summary-card"><span class="mini-kicker">FIABILITÉ DU DOSSIER</span><h4>'+esc(reliability.label||'Non disponible')+'</h4><p class="ca-notice">'+esc(reliability.notice||'')+'</p></div>'+
   '</div>'+
   '<p class="ca-notice">'+esc(d.default_risk?.statement||'')+'</p>');
 }

 function indicatorsSection(d){
  const groups=d.indicators||[];
  if(!groups.length)return section('INDICATEURS FINANCIERS','Les repères de votre dossier','<p class="ca-notice">Aucun indicateur financier communiqué.</p>');
  const body=groups.map(g=>'<div class="ca-group"><h4>'+esc(g.label||'Indicateurs')+'</h4><div class="ca-table-wrap"><table class="ca-table"><thead><tr><th>Indicateur</th><th>Valeur</th><th>Formule</th></tr></thead><tbody>'+
   (g.items||[]).map(item=>'<tr><td>'+esc(item.label||'—')+'</td><td>'+groupValue(item)+'</td><td class="ca-muted">'+esc(item.formula||'—')+'</td></tr>').join('')+
   '</tbody></table></div></div>').join('');
  return section('INDICATEURS FINANCIERS','Les repères de votre dossier',body);
 }

 function scoreSection(d){
  const score=d.score||{};
  const criteria=score.criteria||[];
  const meta='<div class="ca-score-meta">'+
   '<div><span class="mini-kicker">STATUT</span><strong>'+esc(score.status==='available'?'Score calculé':'Score non calculé')+'</strong></div>'+
   '<div><span class="mini-kicker">COUVERTURE DES CRITÈRES</span><strong>'+percent(score.coverage)+'</strong></div>'+
   '<div><span class="mini-kicker">FORMULE</span><strong>'+esc(score.formula||'—')+'</strong></div>'+
  '</div>'+
  '<p class="ca-notice">'+esc(score.notice||'Score conventionnel, non une probabilité de défaut.')+'</p>';
  const table=criteria.length?'<div class="ca-table-wrap"><table class="ca-table"><thead><tr><th>Critère</th><th>Valeur</th><th>Note</th><th>Poids</th><th>Lecture</th></tr></thead><tbody>'+
   criteria.map(c=>{
    const pts=num(c.points);
    const bar=pts===null?'':'<span class="ca-mini-bar" aria-hidden="true"><i style="width:'+Math.max(0,Math.min(100,pts))+'%"></i></span>';
    return '<tr><td><strong>'+esc(c.label||c.id||'—')+'</strong>'+(c.critical?' <span class="badge grey">critique</span>':'')+'</td><td>'+criterionValue(c)+'</td><td>'+(c.available?points(c.points):'Non noté')+bar+'</td><td>'+percent(c.weight)+'</td><td class="ca-muted">'+esc(c.interpretation||'')+'<br><small>'+esc(c.formula||'')+'</small><br><small>'+esc(c.justification||'')+'</small></td></tr>';
   }).join('')+'</tbody></table></div>':'<p class="ca-notice">Aucun critère communiqué.</p>';
  const fav=(score.favorable||[]).length?'<div class="ca-two-col"><div><h4>Points favorables</h4>'+list((score.favorable||[]).map(x=>x.label+' ('+points(x.points)+'/100)'))+'</div><div><h4>Points défavorables</h4>'+list((score.unfavorable||[]).map(x=>x.label+' ('+points(x.points)+'/100)'))+'</div></div>':'';
  const missing=(score.missing_criteria||[]).length?'<h4>Critères non notés</h4><div class="ca-table-wrap"><table class="ca-table"><thead><tr><th>Critère</th><th>Motif</th></tr></thead><tbody>'+(score.missing_criteria||[]).map(x=>'<tr><td>'+esc(x.label||x.criterion)+'</td><td class="ca-muted">'+esc(x.reason||'Valeur indisponible')+'</td></tr>').join('')+'</tbody></table></div>':'';
  return section('SCORE FINANCIER','Un score explicable, jamais une probabilité',meta+table+fav+missing);
 }

 function risksSection(d){
  const risks=d.risks||[],dr=d.default_risk||{};
  const cards=risks.length?risks.map(r=>'<div class="ca-risk"><div class="ca-risk-top"><strong>'+esc(r.label||'Risque')+'</strong>'+badge(r.level,LEVEL[r.level]?.[1]||r.level)+'</div><p>'+esc(r.explanation||'')+'</p>'+
   ((r.evidence||[]).length?'<div class="ca-evidence">'+(r.evidence||[]).map(e=>'<span>'+esc(e.indicator||'')+' : '+esc(e.value??'')+'</span>').join('')+'</div>':'')+
   (r.rule?'<p class="ca-notice">Règle : '+esc(r.rule)+'</p>':'')+'</div>').join(''):'<p class="ca-notice">Aucun risque significatif identifié dans les données fournies.</p>';
  const drivers=(dr.drivers||[]).length?'<h4>Facteurs de risque</h4>'+list(dr.drivers):'';
  const defaultBox='<div class="ca-default-risk"><span class="mini-kicker">RISQUE DE DÉFAUT</span><h4>'+esc(LEVEL[dr.risk_level]?.[1]||dr.risk_level||'Non déterminé')+'</h4><p>'+esc(dr.statement||'')+'</p><p class="ca-notice">Probabilité de défaut calculée : <strong>non</strong> — aucune probabilité calibrée n’est produite.</p>'+drivers+'</div>';
  return section('RISQUES','Les points de vigilance identifiés',cards+defaultBox);
 }

 function scenarioCard(item){
  const s=item||{};
  return '<div class="ca-scenario"><div class="ca-risk-top"><strong>'+esc(s.label||'Scénario')+'</strong>'+badge(s.status,LEVEL[s.status]?.[1]||s.status)+'</div>'+
   '<dl class="ca-mini-def"><div><dt>Marge minimale</dt><dd>'+amount(s.min_margin)+'</dd></div><div><dt>Réserve / trésorerie minimale</dt><dd>'+amount(s.min_reserve)+'</dd></div></dl>'+
   assumptions(s.assumptions)+
   (s.reason?'<p class="ca-notice">'+esc(s.reason)+'</p>':'')+
   (s.source?'<p class="ca-notice">Source : '+esc(s.source)+'</p>':'')+'</div>';
 }
 function scenariosSection(d){
  const s=d.scenarios||{};
  return section('SCÉNARIOS','Des hypothèses explicites, pas des prévisions',
   '<div class="ca-scenarios">'+scenarioCard(s.normal)+scenarioCard(s.adverse)+scenarioCard(s.severe)+'</div>'+
   '<p class="ca-notice">'+esc(s.notice||'Les scénarios sont des hypothèses explicites, pas des prévisions.')+'</p>');
 }

 function reliabilitySection(d){
  const r=d.reliability||{};
  const components=(r.components||[]).map(c=>'<tr><td><strong>'+esc(c.label||c.id)+'</strong></td><td>'+badge(c.status,LEVEL[c.status]?.[1]||c.status)+'</td><td class="ca-muted">'+esc(c.detail||'')+((c.items||[]).length?'<br><small>'+esc((c.items||[]).slice(0,5).join(' · '))+'</small>':'')+'</td></tr>').join('');
  return section('FIABILITÉ DU DOSSIER','Ce qui a été vérifié et ce qui reste à confirmer',
   '<div class="ca-summary-card"><h4>'+esc(r.label||'Non disponible')+'</h4>'+list(r.reasons)+'</div>'+
   (components?'<div class="ca-table-wrap"><table class="ca-table"><thead><tr><th>Composante</th><th>Statut</th><th>Détail</th></tr></thead><tbody>'+components+'</tbody></table></div>':'')+
   ((r.human_verifications||[]).length?'<h4>Vérifications humaines requises</h4>'+list(r.human_verifications):'')+
   '<p class="ca-notice">'+esc(r.notice||'')+'</p>');
 }

 function decisionSection(d){
  const x=d.decision||{},j=x.justifications||{};
  const block=(title,items)=>((items||[]).length?'<div class="ca-justification"><h4>'+esc(title)+'</h4>'+list(items)+'</div>':'');
  return section('DÉCISION','La recommandation et ses justifications',
   '<div class="ca-decision-head"><div><span class="mini-kicker">RECOMMANDATION</span><h4>'+esc(x.label||'Non disponible')+'</h4></div><span class="badge '+(OUTCOME_CLASS[x.outcome]||'grey')+'">'+esc(x.label||x.outcome||'—')+'</span></div>'+
   '<div class="ca-kpis">'+kpi('Garantie demandée',amount(x.requested_guarantee_amount))+kpi('Montant recommandé',amount(x.recommended_guarantee_amount))+kpi('Validation humaine',x.human_approval_status==='pending'?'En attente':'Statut : '+esc(x.human_approval_status||'—'),x.human_approval_required?'Approbation humaine obligatoire':'')+'</div>'+
   '<div class="ca-two-col">'+
    block('Éléments favorables',j.favorable)+block('Éléments défavorables',j.unfavorable)+block('Réserves',j.reserves)+block('Conditions',j.conditions)+block('Points bloquants',j.blocking)+
   '</div>'+
   '<h4>Prochaines étapes</h4>'+list(x.next_steps)+
   '<p class="ca-notice">'+esc(x.notice||'')+'</p>');
 }

 function guaranteeSection(d){
  const g=d.guarantee;
  if(!g)return section('GARANTIE','Aucune garantie constituée à ce jour','<p class="ca-notice">La recommandation de garantie n’est ni une garantie approuvée ni un crédit accordé. Aucune garantie n’a encore été enregistrée pour ce dossier.</p>');
  return section('GARANTIE','Le statut de votre garantie',
   '<div class="ca-decision-head"><div><span class="mini-kicker">RÉFÉRENCE</span><h4>'+esc(g.reference||'Sans référence')+'</h4></div>'+badge(null,g.status_label||g.status)+'</div>'+
   '<div class="ca-kpis">'+kpi('Montant approuvé',amount(g.approved_amount))+kpi('Montant demandé',amount(g.requested_amount))+kpi('Validité',(has(g.effective_from)?date(g.effective_from):'—')+' → '+(has(g.effective_to)?date(g.effective_to):'—'))+'</div>'+
   ((g.conditions||[]).length?'<h4>Conditions associées</h4>'+list(g.conditions):'')+
   '<p class="ca-notice">'+esc(g.official_document_notice||'')+'</p>');
 }

 function documentsSection(d,s){
  const docs=d.documents||[];
  if(!docs.length)return section('DOCUMENTS','Vos documents communiqués','<p class="ca-notice">Aucun document PDF n’est encore disponible pour ce dossier. Les documents sont mis à disposition après leur génération et leur publication par votre analyste.</p>');
  const body=docs.map(doc=>{
   const href=safeHref(doc.download_url);const full=href&&s.api?.base?s.api.base+href:null;
   return '<article class="ca-document"><div><span class="mini-kicker">'+esc(doc.template_id||'DOCUMENT')+'</span><h4>'+esc(doc.title||'Document')+'</h4><p class="ca-notice">Généré le '+dateTime(doc.created_at)+'</p></div>'+
    (full?'<a class="outline ca-download" href="'+esc(full)+'" rel="noopener">Télécharger le PDF ↗</a>':'<span class="badge grey">Téléchargement indisponible</span>')+'</article>';
  }).join('');
  return section('DOCUMENTS','Vos documents communiqués',body);
 }

 function traceabilitySection(d){
  const t=d.traceability||{};
  const rows=[
   ['Version du schéma',d.schema_version],
   ['Analyse décisionnelle',t.decision_id],
   ['Analyse financière source',t.assessment_id],
   ['Moteur décisionnel',t.engine_version],
   ['Règles décisionnelles',t.decision_rules_version||t.rules_version],
   ['Règles financières',t.financial_rules_version],
   ['Règles institutionnelles',t.institutional_rules_version],
   ['Empreinte des données',t.input_sha256],
   ['Empreinte du rapport',t.report_sha256],
   ['Créée le',t.created_at?dateTime(t.created_at):null],
  ];
  const body='<div class="ca-trace">'+rows.map(([k,v])=>'<div>'+esc(k)+'</div><div class="'+(k.includes('Empreinte')?'ca-mono':'')+'">'+(has(v)?esc(v):'Non disponible')+'</div>').join('')+'</div>'+
   '<p class="ca-notice">'+esc(t.notice||'')+'</p>';
  return section('TRAÇABILITÉ','Les références de cette analyse',body);
 }

 function dashboard(d,s){
  const dossier=d.dossier||{},score=d.score||{};
  const scoreNotice=score.status==='available'?'Score conventionnel explicable, non une probabilité de défaut.':'Score non calculé : des données critiques sont manquantes.';
  return '<section class="ca-page" aria-labelledby="ca-title">'+
   '<div class="ca-hero"><div class="ca-hero-main"><span class="mini-kicker">ANALYSE COMMUNIQUÉE · '+esc(dossier.borrower_type||'Dossier')+'</span><h2 id="ca-title">'+esc(d.state_label||'Analyse')+'</h2>'+
    '<p class="ca-lede">'+esc(d.summary?.recommendation||d.decision?.label||'')+'</p>'+
    '<div class="ca-chips"><span class="ca-chip">Dossier '+shortId(dossier.case_id)+'</span><span class="ca-chip">Analysé le '+date(dossier.processed_at)+'</span><span class="ca-chip">Publié le '+date(dossier.published_at)+'</span><span class="ca-chip">'+amount(dossier.requested_amount)+'</span></div>'+
    '<div class="ca-actions"><button class="outline" type="button" data-ca-back>← Revenir à l’analyse</button><button class="outline" type="button" data-ca-print>Imprimer cette page</button></div></div>'+
    '<div class="ca-score-panel">'+ring(score.value)+'<span class="ca-score-label">'+esc(score.label||'Non disponible')+'</span><span class="ca-score-note">'+esc(scoreNotice)+'</span><span class="badge '+(STATE_CLASS[d.state]||'grey')+'">'+esc(d.state_label||'—')+'</span></div></div>'+
   '<div class="ca-confidential" role="note"><strong>Confidentialité.</strong> '+esc(d.confidentiality?.notice||'Seuls les résultats autorisés sont affichés.')+' Les ressources, réserves et engagements globaux de l’institution ne sont pas communiqués.</div>'+
   summarySection(d)+indicatorsSection(d)+scoreSection(d)+risksSection(d)+scenariosSection(d)+reliabilitySection(d)+decisionSection(d)+guaranteeSection(d)+documentsSection(d,s)+traceabilitySection(d)+
   '<p class="ca-notice ca-footer-note">Cette analyse est figée avec les données et règles de son exécution. Elle ne constitue ni une offre de crédit ni une garantie approuvée. Seule une validation humaine habilitée peut approuver une garantie.</p>'+
  '</section>';
 }

 function bind(view){
  view.querySelectorAll('[data-ca-back]').forEach(b=>b.onclick=()=>{location.hash='analysis'});
  view.querySelectorAll('[data-ca-print]').forEach(b=>b.onclick=()=>root.print());
 }

 function message(view,kicker,title,text,withBack=true){
  view.innerHTML='<section class="ca-page"><div class="ca-section ca-empty"><span class="mini-kicker">'+esc(kicker)+'</span><h2>'+esc(title)+'</h2><p>'+esc(text)+'</p>'+(withBack?'<button class="outline" type="button" data-ca-back>← Revenir à l’analyse</button>':'')+'</div></section>';
  bind(view);
 }

 function headings(title,sub){
  const t=document.querySelector('#page-title'),s=document.querySelector('#page-subtitle');
  if(t)t.textContent=title;if(s)s.textContent=sub;
 }

 function addLink(view,s){
  if(view.querySelector('#ca-open'))return;
  const d=root.CreditJourney?.getDraft?.();
  if(!d?.remote?.id||s.audience!=='applicant')return;
  const panel=view.querySelector('.form-panel')||view.querySelector('.empty-analysis');
  if(!panel)return;
  const box=document.createElement('div');box.className='ca-cta';box.id='ca-open';
  box.innerHTML='<div><span class="mini-kicker">ANALYSE DÉTAILLÉE</span><h3>Voir l’analyse complète communiquée.</h3><p>Score explicable, indicateurs, risques, scénarios, décision, garantie, documents et traçabilité.</p></div><button class="primary" type="button">Ouvrir l’analyse détaillée →</button>';
  box.querySelector('button').onclick=()=>{location.hash='analyse-complete'};
  panel.append(box);
 }

 async function render(view,s){
  const d=root.CreditJourney?.getDraft?.();
  headings('Votre analyse, en détail.','Résultats communiqués par votre analyste. Aucun accord de crédit.');
  if(!d?.remote?.id){message(view,'ANALYSE COMMUNIQUÉE','Aucun dossier sélectionné.','Ouvrez d’abord un dossier depuis vos demandes pour consulter l’analyse communiquée.');return}
  if(!s.api){message(view,'ANALYSE COMMUNIQUÉE','Service momentanément indisponible.','Reconnectez-vous pour consulter votre analyse.');return}
  view.innerHTML='<section class="ca-page"><div class="ca-section ca-empty"><span class="mini-kicker">ANALYSE COMMUNIQUÉE</span><h2>Préparation de votre analyse…</h2><p>Chargement des résultats autorisés pour ce dossier.</p></div></section>';
  let data;
  try{
   data=await s.api.request('/'+d.core+'/'+encodeURIComponent(d.remote.id)+'/client-analysis');
  }catch(e){
   if(!document.contains(view)||view!==document.querySelector('#view')||!location.hash.startsWith('#analyse-complete'))return;
   if(e.status===404)message(view,'ANALYSE COMMUNIQUÉE','Aucune analyse communiquée.','Votre analyse n’a pas encore été publiée par votre analyste. Elle apparaîtra ici dès sa communication.');
   else if(e.status===403)message(view,'ANALYSE COMMUNIQUÉE','Accès non autorisé.','Vous ne disposez pas des droits nécessaires pour consulter cette analyse.');
   else message(view,'ANALYSE COMMUNIQUÉE','Analyse indisponible.','Le service n’a pas pu fournir votre analyse. Réessayez dans un instant.');
   return;
  }
  if(!document.contains(view)||view!==document.querySelector('#view')||!location.hash.startsWith('#analyse-complete'))return;
  if(data?.confidentiality?.institutional_capacity_exposed!==false||data?.confidentiality?.portfolio_exposed!==false){
   message(view,'ANALYSE COMMUNIQUÉE','Analyse indisponible.','La charge utile reçue ne respecte pas les règles de confidentialité. Aucun élément n’est affiché.');
   return;
  }
  view.innerHTML=dashboard(data,s);
  bind(view);
 }

 function mount(view,route){
  const s=root.CreditServices;
  if(!view||!s||s.staff)return;
  const r=route||(location.hash.slice(1).split('/')[0]||'overview');
  if(r==='analysis'){addLink(view,s);return}
  if(r!=='analyse-complete')return;
  render(view,s);
 }

 root.CreditClientAnalysis=Object.freeze({mount});
})(typeof window==='undefined'?globalThis:window);
