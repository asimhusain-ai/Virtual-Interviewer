// Theme handling: follow device preference only
(function () {
  const THEMES = { light: 'theme-light', dark: 'theme-dark' };
  const THEME_CLASSES = Object.values(THEMES);
  const STORAGE_KEY = 'iv_theme';
  const body = document.body;
  if (!body) return;

  const mediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const getPreferredTheme = () => (mediaQuery && mediaQuery.matches ? THEMES.dark : THEMES.light);
  const getStoredTheme = () => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return THEME_CLASSES.includes(stored) ? stored : null;
    } catch (e) {
      return null;
    }
  };

  const applyTheme = (theme, persist = false) => {
    const next = THEME_CLASSES.includes(theme) ? theme : THEMES.light;
    body.classList.remove(...THEME_CLASSES);
    body.classList.add(next);
    body.dataset.theme = next;
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next === THEMES.dark ? 'dark' : 'light';
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {
        // ignore storage errors
      }
    }
    document.dispatchEvent(new CustomEvent('iv-theme-change', { detail: { theme: next } }));
  };

  const applyPreferred = () => {
    const stored = getStoredTheme();
    applyTheme(stored || getPreferredTheme());
  };

  applyPreferred();

  if (mediaQuery) {
    const handleMediaChange = (event) => {
      const stored = getStoredTheme();
      if (stored) return;
      applyTheme(event.matches ? THEMES.dark : THEMES.light);
    };
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleMediaChange);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handleMediaChange);
    }
  }

  const toggleTheme = () => {
    const current = body.classList.contains(THEMES.dark) ? THEMES.dark : THEMES.light;
    const next = current === THEMES.dark ? THEMES.light : THEMES.dark;
    applyTheme(next, true);
  };

  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-theme-toggle]');
    if (!toggle) return;
    event.preventDefault();
    toggleTheme();
  });

  window.ivTheme = {
    currentTheme: () => (body.classList.contains(THEMES.dark) ? THEMES.dark : THEMES.light),
    setTheme: (theme) => applyTheme(theme, true),
    toggle: () => toggleTheme(),
    refresh: () => applyPreferred()
  };
})();
