'use strict';
/* Affichage uniquement : montants, totaux et proportions proviennent du serveur. */
(() => {
  const colors = { necessary: '#15c781', existing: '#ff8658', requested: '#f251aa', remaining: '#7564ff', initial: '#94a3b8', increase: '#15c781', decrease: '#ff8658', shortfall: '#f251aa', funds: '#7564ff' };
  const modes = ['capacity', 'debt', 'liquidity'];
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const amount = value => typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value) ? new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(value) : '—';
  const date = value => new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(value));
  let cleanup = null;
  function shell() {
    return `<section class="budget-showcase" aria-labelledby="budget-showcase-title"><div class="budget-intro"><span class="budget-eyebrow">LES REPÈRES DE VOTRE FINANCEMENT</span><h2 id="budget-showcase-title">Votre projet.<br>Ses marges de manœuvre.</h2><p>Capacité de remboursement, échéances et ressources mobilisables : les points à examiner avant de financer votre projet.</p><a class="budget-link" href="#demande">Préparer mon financement <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 13 13 3M3 3h10v10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></a><p class="budget-disclaimer">Des indicateurs expliqués.<br>La décision de crédit reste humaine.</p></div><div class="budget-card" id="home-budget-card" aria-busy="true"></div></section>`;
  }
  function mount(view) {
    cleanup?.(); cleanup = null;
    const host = view.querySelector('#home-budget-card');
    if (!host) return;
    let current = true, data = null, periodIndex = 0, mode = 'capacity', loading = false, failure = false;
    cleanup = () => { current = false; };
    function draw() {
      const row = data?.periods[periodIndex];
      const group = row?.[mode];
      const core = data?.core || window.CreditJourney?.getDraft()?.core;
      const business = core === 'businesses';
      const labels = { capacity: 'Capacité', debt: business ? 'Dette' : 'Échéances', liquidity: business ? 'Trésorerie' : 'Réserve' };
      const intro = host.closest('.budget-showcase').querySelector('.budget-intro');
      intro.querySelector('h2').innerHTML = business ? 'Financer l’activité.<br>Préserver sa trésorerie.' : core === 'individuals' ? 'Emprunter.<br>Préserver votre équilibre.' : 'Votre projet.<br>Ses marges de manœuvre.';
      intro.querySelector('.budget-eyebrow').textContent = business ? 'ANALYSE DU CRÉDIT · ENTREPRISES / PME' : core === 'individuals' ? 'ANALYSE DU CRÉDIT · PARTICULIERS' : 'LES REPÈRES DE VOTRE FINANCEMENT';
      intro.querySelector('h2 + p').textContent = business ? 'Les flux disponibles pour rembourser, le service de la dette et la trésorerie projetée de votre activité.' : core === 'individuals' ? 'La marge de votre ménage après crédit, les échéances à couvrir et l’évolution de votre réserve mobilisable.' : 'Capacité de remboursement, échéances et ressources mobilisables : les points à examiner avant de financer votre projet.';
      const categories = group?.segments || [
        ...(mode === 'liquidity' ? [{id:'initial',label:'Solde initial mobilisable',value:null}] : []),
        ...(mode !== 'liquidity' ? [{ id: 'existing', label: 'Échéances existantes', value: null }, { id: 'requested', label: 'Échéance du nouveau crédit', value: null }] : [])
      ];
      let cursor = 0;
      const arcs = categories.map(segment => {
        const share = Number(segment.percentage);
        if (!Number.isFinite(share) || share <= 0 || share > 100) return '';
        const gap = Math.min(2.6, share * .2);
        const length = share - gap;
        const offset = -cursor - gap / 2;
        cursor += share;
        return `<circle class="budget-arc" cx="160" cy="160" r="118" pathLength="100" fill="none" stroke="${colors[segment.id] || '#94a3b8'}" stroke-width="14" stroke-linecap="round" stroke-dasharray="${length} ${100 - length}" stroke-dashoffset="${offset}" transform="rotate(-90 160 160)"/>`;
      }).join('');
      const caption = loading ? 'Chargement du dossier' : failure ? 'Résultats indisponibles' : !row ? 'Aucun résultat financier disponible' : group?.status === 'incomplete' ? 'Données à compléter' : row.basis === 'forecast' ? 'Prévisions du dossier' : row.basis === 'observed' ? 'Données observées' : 'Nature à confirmer';
      host.setAttribute('aria-busy', String(loading));
      host.innerHTML = `${data?.case_label ? '<p class="budget-case-label">Dossier · ' + escape(data.case_label) + '</p>' : ''}<div class="budget-tabs" role="tablist" aria-label="Repères du financement">${modes.map((key, index) => `<button type="button" role="tab" id="budget-tab-${key}" aria-controls="budget-panel" aria-selected="${mode === key}" tabindex="${mode === key ? '0' : '-1'}" data-budget-mode="${key}" data-index="${index}">${labels[key]}</button>`).join('')}</div><div id="budget-panel" role="tabpanel" aria-labelledby="budget-tab-${mode}"><div class="budget-ring"><svg viewBox="0 0 320 320" role="img" aria-label="${arcs ? 'Répartition ' + escape(group.title.toLocaleLowerCase('fr')) + ', ' + escape(date(row.period)) : group?.status === 'zero' ? 'Total nul pour cette période, aucune part à représenter' : 'Répartition indisponible : renseignez et faites analyser votre dossier'}"><circle cx="160" cy="160" r="118" fill="none" stroke="#303033" stroke-width="14" ${arcs ? '' : 'stroke-dasharray="5 3" pathLength="100"'}/>${arcs}</svg><div class="budget-ring-center" aria-live="polite"><span>${escape(group?.title || ({capacity:business?'Marge après dette':'Marge après crédit',debt:'Service de la dette',liquidity:business?'Trésorerie projetée':'Réserve projetée'})[mode])}</span><strong class="${(mode === 'capacity' && row?.deficit || mode === 'liquidity' && group?.negative) ? 'budget-negative' : ''}">${amount(group?.value)}</strong><small>${group?.value !== null && group?.value !== undefined ? 'FCFA' : 'À renseigner'}</small>${row ? `<span class="budget-ring-date">${escape(date(row.period))}</span>` : ''}</div></div><div class="budget-period"><span>Période</span><select id="budget-period" aria-label="Période du financement" ${row ? '' : 'disabled'}>${data?.periods.map((p, index) => `<option value="${index}" ${index === periodIndex ? 'selected' : ''}>${escape(date(p.period))}</option>`).join('') || '<option>À sélectionner</option>'}</select><button type="button" id="budget-refresh" aria-label="Actualiser les indicateurs du financement" ${loading ? 'disabled' : ''}>↻</button></div><p class="budget-caption" role="status">${escape(caption)}</p>${(row?.deficit || group?.negative) ? '<p class="budget-deficit">'+(group?.negative?'Attention : le solde projeté est négatif.':'Attention : la capacité de remboursement est insuffisante sur cette période.')+'</p>' : ''}<p class="credit-view-explanation">${escape(group?.explanation || 'Les indicateurs apparaîtront après analyse et autorisation de communication.')}</p>${mode === 'capacity' && group ? `<dl class="credit-readouts"><div><dt>Disponible avant dette</dt><dd>${amount(group.available_before_debt)} FCFA</dd></div><div><dt>Échéances à couvrir</dt><dd>${amount(group.debt_due)} FCFA</dd></div></dl>` : ''}<div class="budget-list-heading"><h3>${mode === 'capacity' ? 'Échéances et marge restante' : mode === 'debt' ? 'Les échéances à couvrir' : 'L’évolution des liquidités'}</h3><a href="#analysis">Voir l’analyse <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 13 13 3M3 3h10v10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></a></div><ul class="budget-categories">${categories.map(segment => `<li><span class="budget-category-dot" style="--category-color:${colors[segment.id] || '#94a3b8'}" aria-hidden="true"></span><span class="budget-category-name">${escape(segment.label)}</span><span class="budget-category-value">${segment.value === null || segment.value === undefined ? 'Non disponible' : amount(segment.value) + ' FCFA'}${segment.percentage !== null && segment.percentage !== undefined ? `<small>${amount(segment.percentage)} %</small>` : ''}</span></li>`).join('')}</ul><p class="budget-source">${escape(data?.notice || 'Renseignez votre dossier pour afficher les résultats autorisés de son analyse. Aucun montant n’est supposé.')}</p></div>`;
      host.querySelectorAll('[data-budget-mode]').forEach(button => {
        button.onclick = () => { mode = button.dataset.budgetMode; draw(); host.querySelector('#budget-tab-' + mode).focus({ preventScroll: true }); };
        button.onkeydown = event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const index = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (modes.indexOf(mode) + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
          mode = modes[index]; draw(); host.querySelector('#budget-tab-' + mode).focus({ preventScroll: true });
        };
      });
      host.querySelector('#budget-period').onchange = event => { periodIndex = Number(event.target.value); draw(); host.querySelector('#budget-period').focus({ preventScroll: true }); };
      host.querySelector('#budget-refresh').onclick = refresh;
    }
    async function refresh() {
      const services = window.CreditServices;
      const draft = window.CreditJourney?.getDraft();
      data = null; failure = false;
      if (!services?.ready || !draft?.remote?.id || !services.readBudget) { loading = false; draw(); return; }
      loading = true; draw();
      try {
        const result = await services.readBudget(draft);
        if (!current || !host.isConnected || window.CreditJourney?.getDraft() !== draft || !services.ready) return;
        data = result;
        if (periodIndex >= (data?.periods.length || 0)) periodIndex = 0;
      } catch (error) { if (error.status !== 404) failure = true; }
      finally { if (current && host.isConnected) { loading = false; draw(); } }
    }
    draw(); refresh();
  }
  window.CreditBudget = { shell, mount };
})();
