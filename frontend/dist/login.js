'use strict';
(() => {
  window.CreditHomeVideos?.mount(document);
  const form = document.getElementById('public-login');
  const message = document.getElementById('login-message');
  const label = document.getElementById('login-button-label');
  const submit = form.querySelector('button[type=submit]');
  const password = document.getElementById('login-password');
  const toggle = document.getElementById('password-toggle');
  const config = window.CREDIT_RUNTIME || {};
  let busy = false;
  function endpoint(path) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || url.username || url.password) throw new Error('Configuration de connexion invalide.');
    return url;
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      return await fetch(endpoint(path), { ...options, credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal });
    } finally { clearTimeout(timer); }
  }
  function enter(user) {
    const route = ['bank_agent', 'bank_manager'].includes(user?.role) ? 'bank-inbox' : 'overview';
    // Destination interne fixe : aucun paramètre returnTo ni rôle choisi dans le formulaire.
    location.replace('/platform.html#' + route);
  }
  toggle.addEventListener('click', () => {
    const visible = password.type === 'password';
    password.type = visible ? 'text' : 'password';
    toggle.textContent = visible ? 'Masquer' : 'Afficher';
    toggle.setAttribute('aria-pressed', String(visible));
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true; submit.disabled = true; label.textContent = 'Connexion…'; message.hidden = true; message.classList.remove('success');
    try {
      if (!config.loginUrl) throw new Error('La connexion est momentanément indisponible.');
      const body = { username: form.elements.username.value.trim(), password: password.value };
      const response = await request(config.loginUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(response.status === 429 ? 'Trop de tentatives. Patientez avant de réessayer.' : response.status === 401 ? 'Identifiant ou mot de passe incorrect.' : 'La connexion est momentanément indisponible. Réessayez plus tard.');
      const data = await response.json();
      if (!data?.user?.id) throw new Error('La session n’a pas pu être confirmée.');
      password.value = ''; enter(data.user);
    } catch (error) {
      message.textContent = error.name === 'AbortError' ? 'Le service met trop de temps à répondre. Vérifiez votre connexion puis réessayez.' : error instanceof TypeError ? 'Connexion impossible. Vérifiez votre réseau puis réessayez.' : error.message;
      message.hidden = false; message.focus();
    } finally { busy = false; submit.disabled = false; label.textContent = 'Se connecter'; }
  });
  const tabs = [...document.querySelectorAll('.auth-tabs [role=tab]')];
  function selectTab(id, focus = true) {
    for (const tab of tabs) {
      const active = tab.id === id;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
      if (active && focus) tab.focus();
    }
  }
  tabs.forEach((tab, index) => {
    tab.onclick = () => selectTab(tab.id);
    tab.onkeydown = event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      selectTab(tabs[target].id);
    };
  });
  if (location.hash === '#register') selectTab('register-tab', false);
  const registration = document.getElementById('public-register');
  const identifier = document.getElementById('register-identifier');
  const registerMessage = document.getElementById('register-message');
  const registerButton = registration.querySelector('button[type=submit]');
  let registering = false;
  function updateIdentifier() {
    const phone = registration.elements.channel.value === 'phone';
    identifier.type = phone ? 'tel' : 'email';
    identifier.autocomplete = phone ? 'tel' : 'email';
    identifier.inputMode = phone ? 'tel' : 'email';
    identifier.placeholder = phone ? '+226 70 00 00 00' : 'vous@exemple.com';
    document.getElementById('identifier-label').textContent = phone ? 'Numéro de téléphone' : 'Adresse e-mail';
    identifier.value = '';
  }
  registration.addEventListener('change', event => {if (event.target.name === 'channel') updateIdentifier();});
  registration.elements.password_confirmation.addEventListener('input', () => registration.elements.password_confirmation.setCustomValidity(''));
  registration.addEventListener('submit', async event => {
    event.preventDefault();
    if (registering) return;
    const data = Object.fromEntries(new FormData(registration));
    registration.elements.password_confirmation.setCustomValidity(data.password === data.password_confirmation ? '' : 'Les mots de passe doivent correspondre.');
    if (!registration.reportValidity()) return;
    registering = true; registerButton.disabled = true; registerMessage.hidden = true;
    document.getElementById('register-button-label').textContent = 'Création…';
    try {
      if (!config.registrationEndpoint) throw new Error('La création de compte n’est pas encore activée.');
      const response = await request(config.registrationEndpoint, {method:'POST', headers:{'Content-Type':'application/json', Accept:'application/json'}, body:JSON.stringify(data)});
      if (response.status !== 202) throw new Error(response.status === 429 ? 'Trop de tentatives. Patientez avant de réessayer.' : response.status === 422 ? 'Vérifiez vos coordonnées et les mots de passe (12 caractères minimum).' : 'La création de compte est momentanément indisponible.');
      const result = await response.json();
      if (result.status !== 'accepted') throw new Error('La création n’a pas pu être confirmée.');
      form.elements.username.value = data.identifier.trim();
      registration.reset(); updateIdentifier();
      selectTab('login-tab', false);
      message.textContent = 'Connectez-vous avec vos coordonnées et votre mot de passe. Un compte déjà existant n’est pas modifié.';
      message.classList.add('success'); message.hidden = false; message.focus();
    } catch (error) {
      registerMessage.textContent = error.name === 'AbortError' ? 'Le service met trop de temps à répondre. Réessayez plus tard.' : error instanceof TypeError ? 'Connexion impossible. Vérifiez votre réseau puis réessayez.' : error.message;
      registerMessage.hidden = false; registerMessage.focus();
    } finally {registering = false; registerButton.disabled = false; document.getElementById('register-button-label').textContent = 'Créer mon compte';}
  });
  // Reprendre une session valide, sans stocker de jeton dans le navigateur.
  if (config.sessionEndpoint) request(config.sessionEndpoint).then(async response => {
    if (response.ok) { const data = await response.json(); if (data?.user?.id && !busy) enter(data.user); }
  }).catch(() => {});
})();
