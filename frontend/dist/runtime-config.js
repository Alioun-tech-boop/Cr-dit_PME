/* Configuration publique de déploiement. Aucun secret. La passerelle doit être de même origine. */
window.CREDIT_RUNTIME = Object.freeze({
  environment: 'local',
  apiBaseUrl: '/api',
  sessionEndpoint: '/auth/session',
  profileEndpoint: '/auth/profile',
  loginUrl: '/auth/login',
  logoutUrl: '/auth/logout',
  publishedAssessmentEndpoint: '/{core}/{id}/published-assessment',
  csrfTokenEndpoint: '/auth/csrf',
  requestTimeoutMs: 20000,
  applicationVersion: '1.0.0-rc.1'
});
