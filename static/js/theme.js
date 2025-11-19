// Theme handling aligned with the Uiverse checkbox toggle
(function () {
  const STORAGE_KEY = 'iv_theme';
  const THEMES = { light: 'theme-light', dark: 'theme-dark' };
  const THEME_CLASSES = Object.values(THEMES);
  const body = document.body;
  if (!body) return;

  const mediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  let userOverride = false;
  let switchEls = [];

  const isThemeClass = (value) => THEME_CLASSES.includes(value);
  const getStoredTheme = () => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isThemeClass(stored) ? stored : null;
  };
  const getPreferredTheme = () => (mediaQuery && mediaQuery.matches ? THEMES.dark : THEMES.light);
  const getCurrentTheme = () => (body.classList.contains(THEMES.dark) ? THEMES.dark : THEMES.light);

  const syncSwitches = () => {
    const isLight = getCurrentTheme() === THEMES.light;
    switchEls.forEach((el) => {
      el.checked = isLight;
      el.setAttribute('aria-checked', isLight ? 'true' : 'false');
    });
  };

  const applyTheme = (theme, persist = false) => {
    const next = isThemeClass(theme) ? theme : THEMES.light;
    body.classList.remove(...THEME_CLASSES);
    body.classList.add(next);
    body.dataset.theme = next;

    if (persist) {
      localStorage.setItem(STORAGE_KEY, next);
      userOverride = true;
    }

    syncSwitches();
    document.dispatchEvent(new CustomEvent('iv-theme-change', { detail: { theme: next } }));
  };

  const storedTheme = getStoredTheme();
  if (storedTheme) {
    userOverride = true;
    applyTheme(storedTheme, false);
  } else {
    applyTheme(getPreferredTheme(), false);
  }

  const handleSwitchChange = (event) => {
    const nextTheme = event.target.checked ? THEMES.light : THEMES.dark;
    applyTheme(nextTheme, true);
  };

  const initSwitches = () => {
    switchEls = Array.from(document.querySelectorAll('#switch'));
    switchEls.forEach((el) => {
      if (el.dataset.ivToggleInit === '1') {
        return;
      }
      el.dataset.ivToggleInit = '1';
      el.setAttribute('role', 'switch');
      el.setAttribute('aria-label', 'Toggle light and dark theme');
      el.addEventListener('change', handleSwitchChange);
    });
    syncSwitches();
  };

  initSwitches();

  if (!switchEls.length) {
    const observer = new MutationObserver(() => {
      initSwitches();
      if (switchEls.length) {
        observer.disconnect();
      }
    });
    observer.observe(body, { childList: true, subtree: true });
  }

  const handleMediaChange = (event) => {
    if (userOverride) return;
    applyTheme(event.matches ? THEMES.dark : THEMES.light, false);
  };

  if (mediaQuery) {
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleMediaChange);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handleMediaChange);
    }
  }

  window.ivTheme = {
    applyTheme: (theme) => applyTheme(theme, true),
    toggleTheme: () => {
      const next = getCurrentTheme() === THEMES.dark ? THEMES.light : THEMES.dark;
      applyTheme(next, true);
    },
    currentTheme: getCurrentTheme,
    refresh: () => {
      initSwitches();
      syncSwitches();
    }
  };
})();
