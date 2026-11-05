'use strict';
(() => {
  // Anciennes URL à fragment : conserver les liens de dossiers déjà distribués.
  const anchors = new Set(['#fonctionnement', '#pour-vous', '#approche', '#contenu', '#haut']);
  if (location.hash && !anchors.has(location.hash)) {
    location.replace('/platform.html' + location.search + location.hash);
    return;
  }
  window.CreditHomeVideos?.mount(document);
})();
