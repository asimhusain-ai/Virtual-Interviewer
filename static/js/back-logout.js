// Auto-logout on browser back navigation for authenticated users
(function () {
  if (!window.IS_AUTHENTICATED) return;

  try {
    history.pushState({ ivConfirmBack: true }, '', window.location.href);
  } catch (e) {
    // ignore history errors
  }

  window.addEventListener('popstate', () => {
    window.location.href = '/logout';
  });
})();
