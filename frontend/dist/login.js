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
    busy = true; submit.disabled = true; label.textContent = 'Connexion…'; message.hidden = true;
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
  // Reprendre une session valide, sans stocker de jeton dans le navigateur.
  if (config.sessionEndpoint) request(config.sessionEndpoint).then(async response => {
    if (response.ok) { const data = await response.json(); if (data?.user?.id && !busy) enter(data.user); }
  }).catch(() => {});
})();
