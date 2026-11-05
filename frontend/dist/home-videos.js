'use strict';
/* Séquences locales : aucune requête vers une plateforme vidéo ou publicitaire. */
(() => {
  const entries = new Map();
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const connection = navigator.connection;
  function autoplayAllowed() {
    const preference = document.documentElement.dataset.motion;
    return preference !== 'reduced' && (preference === 'full' || !motion.matches) && !connection?.saveData;
  }
  function label(entry) {
    const paused = entry.video.paused;
    entry.button.textContent = paused ? '▶ Lire' : 'Ⅱ Pause';
    entry.button.setAttribute('aria-label', (paused ? 'Lire la vidéo : ' : 'Mettre en pause la vidéo : ') + entry.title);
    entry.button.setAttribute('aria-pressed', String(!paused));
  }
  function sync(entry) {
    const video = entry.video;
    if (!video.isConnected || document.hidden || !entry.visible || entry.userPaused || (!entry.userStarted && !autoplayAllowed())) {
      video.pause();
      label(entry);
      return;
    }
    if (entry.failed || entry.pending || entry.blocked) return;
    if (!video.getAttribute('src')) video.src = video.dataset.src;
    video.muted = true;
    entry.pending = true;
    video.play().then(() => {
      entry.pending = false;
      // Une navigation, un défilement ou un changement de préférence peut précéder play().
      if (!video.isConnected || document.hidden || !entry.visible || entry.userPaused || (!entry.userStarted && !autoplayAllowed())) video.pause();
      label(entry);
    }).catch(() => {
      entry.pending = false;
      entry.blocked = true;
      label(entry);
    });
  }
  const visibility = new IntersectionObserver(changes => {
    for (const change of changes) {
      const entry = entries.get(change.target);
      if (entry) { entry.visible = change.isIntersecting && change.intersectionRatio >= 0.12; sync(entry); }
    }
  }, { threshold: 0.12 });
  function syncAll() { for (const entry of entries.values()) sync(entry); }
  new MutationObserver(() => {
    if (!autoplayAllowed()) for (const entry of entries.values()) entry.userStarted = false;
    syncAll();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion'] });
  document.addEventListener('visibilitychange', syncAll);
  motion.addEventListener('change', syncAll);
  connection?.addEventListener('change', syncAll);
  window.CreditHomeVideos = {
    mount(root) {
      for (const [video] of entries) {
        if (!video.isConnected) { video.pause(); visibility.unobserve(video); entries.delete(video); }
      }
      for (const video of root.querySelectorAll('video.home-video')) {
        if (entries.has(video)) continue;
        const button = video.closest('.story').querySelector('.home-video-toggle');
        const entry = { video, button, title: video.dataset.title, visible: false, pending: false, failed: false, blocked: false, userPaused: false, userStarted: false };
        entries.set(video, entry);
        video.muted = true;
        video.addEventListener('playing', () => label(entry));
        video.addEventListener('pause', () => label(entry));
        video.addEventListener('error', () => {
          entry.failed = true;
          video.pause();
          button.textContent = 'Vidéo indisponible';
          button.setAttribute('aria-label', 'Vidéo indisponible ; image de présentation affichée');
          button.disabled = true;
        });
        button.onclick = () => {
          if (video.paused) { entry.userPaused = false; entry.userStarted = true; entry.blocked = false; }
          else { entry.userPaused = true; entry.userStarted = false; }
          sync(entry);
        };
        label(entry);
        visibility.observe(video);
      }
    }
  };
})();
