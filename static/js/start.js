// Start page interactions: socials, magnetic motion, navigation
(function () {
  const themeManager = window.ivTheme;
  if (themeManager && typeof themeManager.refresh === 'function') {
    themeManager.refresh();
  }

  const logoutToast = document.getElementById('logout-toast');
  if (logoutToast && logoutToast.dataset.logoutActive === '1') {
    let dismissed = false;
    let hideTimer;
    const dismissToast = () => {
      if (dismissed) return;
      dismissed = true;
      if (hideTimer) {
        clearTimeout(hideTimer);
      }
      logoutToast.setAttribute('aria-hidden', 'true');
      logoutToast.classList.remove('show');
      document.removeEventListener('keydown', handleKeyDown);
      setTimeout(() => {
        if (logoutToast && logoutToast.parentNode) {
          logoutToast.parentNode.removeChild(logoutToast);
        }
      }, 360);
    };

    const dismissButton = logoutToast.querySelector('[data-dismiss-toast]');
    if (dismissButton) {
      dismissButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        dismissToast();
      });
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        dismissToast();
      }
    };
    document.addEventListener('keydown', handleKeyDown);

    logoutToast.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      logoutToast.classList.add('show');
      hideTimer = window.setTimeout(dismissToast, 3000);
    });
    logoutToast.dataset.logoutActive = '0';
  }

  const authToast = document.querySelector('.auth-toast.show');
  if (authToast) {
    const hideAuthToast = () => {
      authToast.classList.remove('show');
      authToast.setAttribute('aria-hidden', 'true');
      setTimeout(() => {
        if (authToast && authToast.parentNode) {
          authToast.parentNode.removeChild(authToast);
        }
      }, 360);
    };
    authToast.setAttribute('aria-hidden', 'false');
    setTimeout(hideAuthToast, 5000);
  }

  const signupPasswordInput = document.getElementById('signupPassword');
  if (signupPasswordInput) {
    const passwordField = signupPasswordInput.closest('.auth-field');
    const passwordError = passwordField ? passwordField.querySelector('[data-password-error]') : null;
    const signupForm = signupPasswordInput.form || null;
    const MIN_PASSWORD_LENGTH = 8;
    let passwordAttempted = false;

    const togglePasswordError = (shouldShow) => {
      if (!passwordError) return;
      passwordError.classList.toggle('is-visible', shouldShow);
    };

    const evaluatePassword = (forceShow = false) => {
      if (forceShow) {
        passwordAttempted = true;
      }

      const valueLength = signupPasswordInput.value.trim().length;
      const isValid = valueLength >= MIN_PASSWORD_LENGTH;

      if (passwordAttempted) {
        togglePasswordError(!isValid);
      }

      signupPasswordInput.setCustomValidity(isValid ? '' : ' ');
      return isValid;
    };

    signupPasswordInput.addEventListener('input', () => {
      if (!passwordAttempted) {
        signupPasswordInput.setCustomValidity('');
        return;
      }

      const isValid = signupPasswordInput.value.trim().length >= MIN_PASSWORD_LENGTH;
      togglePasswordError(!isValid);
      signupPasswordInput.setCustomValidity(isValid ? '' : ' ');
    });

    signupPasswordInput.addEventListener('blur', () => {
      if (signupPasswordInput.value.trim().length === 0) {
        togglePasswordError(false);
        signupPasswordInput.setCustomValidity('');
        return;
      }

      passwordAttempted = true;
      evaluatePassword(true);
    });

    if (signupForm) {
      signupForm.addEventListener('submit', (event) => {
        const isValid = evaluatePassword(true);
        if (!isValid) {
          event.preventDefault();
          if (typeof event.stopImmediatePropagation === 'function') {
            event.stopImmediatePropagation();
          }
          signupPasswordInput.focus({ preventScroll: true });
        }
      }, true);
    }
  }

  // Detect demo mode on arrival (e.g. landing?demo=1) and add a body class so UI elements
  // like the Dashboard button can be hidden while in demo mode.
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get('demo') === '1') {
      document.body.classList.add('demo-mode');
    }
  } catch (e) {
    // ignore in browsers without URLSearchParams (very old)
  }

  const openSocialLink = (url) => {
    if (!url) return;
    try {
      window.open(url, '_blank', 'noopener');
    } catch (error) {
      console.warn('Unable to open social link', error);
    }
  };

  const socialColumn = document.getElementById('social-stack');
  if (socialColumn) {
    setTimeout(() => {
      socialColumn.classList.add('show');
    }, 3000);

    socialColumn.addEventListener('click', (event) => {
      const button = event.target.closest('.social-icon');
      if (!button) return;
      const href = button.dataset.url || button.getAttribute('data-href') || button.getAttribute('href');
      openSocialLink(href);
    });
  }

  const adminDock = document.querySelector('.admin-dock');
  if (adminDock) {
    const badge = adminDock.querySelector('.admin-badge');
    const linkGroup = adminDock.querySelector('.admin-links');
    const socialButtons = Array.from(adminDock.querySelectorAll('.admin-links .social-icon'));

    let dockOpen = false;

    const shiftFocusOutOfLinks = () => {
      if (!linkGroup) return;
      const active = document.activeElement;
      if (active && linkGroup.contains(active)) {
        if (badge && typeof badge.focus === 'function') {
          badge.focus({ preventScroll: true });
        } else if (typeof active.blur === 'function') {
          active.blur();
        }
      }
    };

    const setDockState = (open) => {
      const nextState = !!open;
      if (!nextState) {
        shiftFocusOutOfLinks();
      }

      dockOpen = nextState;
      adminDock.classList.toggle('is-open', dockOpen);
      if (badge) {
        badge.setAttribute('aria-expanded', dockOpen ? 'true' : 'false');
      }
      if (linkGroup) {
        linkGroup.setAttribute('aria-hidden', dockOpen ? 'false' : 'true');
      }
      socialButtons.forEach((button) => {
        button.tabIndex = dockOpen ? 0 : -1;
      });
    };

    const toggleDock = () => setDockState(!dockOpen);
    const closeDock = () => setDockState(false);

    const handleBadgeClick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleDock();
    };

    const handleBadgeKeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleDock();
      } else if (event.key === 'Escape') {
        closeDock();
        if (badge) {
          badge.blur();
        }
      }
    };

    const handleSocialClick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      const button = event.currentTarget;
      if (!button) return;
      const href = button.dataset.url || button.getAttribute('data-href') || button.getAttribute('href');
      openSocialLink(href);
    };

    const handleSocialKeydown = (event) => {
      if (event.key === 'Escape') {
        closeDock();
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        const button = event.currentTarget;
        const href = button.dataset.url || button.getAttribute('data-href') || button.getAttribute('href');
        openSocialLink(href);
      }
    };

    const handleDocumentClick = (event) => {
      if (!dockOpen) return;
      if (!adminDock.contains(event.target)) {
        closeDock();
      }
    };

    const handleDocumentKeydown = (event) => {
      if (!dockOpen) return;
      if (event.key === 'Escape') {
        closeDock();
      }
    };

    if (badge) {
      badge.addEventListener('click', handleBadgeClick);
      badge.addEventListener('keydown', handleBadgeKeydown);
    }

    socialButtons.forEach((button) => {
      button.addEventListener('click', handleSocialClick);
      button.addEventListener('keydown', handleSocialKeydown);
    });

    document.addEventListener('click', handleDocumentClick);
    document.addEventListener('keydown', handleDocumentKeydown);

    setDockState(false);
  }

  const icons = Array.from(document.querySelectorAll('.social-icon'));
  const magnetSettings = { radius: 120, strength: 0.6, maxOffset: 24 };
  const states = new Map();

  const ensureState = (el) => {
    if (states.has(el)) return states.get(el);
    const state = {
      target: { x: 0, y: 0 },
      current: { x: 0, y: 0 },
      pending: null,
      magnetFrame: null,
      smoothFrame: null
    };
    states.set(el, state);
    return state;
  };

  const applyStyles = (el, state) => {
    el.style.setProperty('--mag-x', state.current.x.toFixed(2) + 'px');
    el.style.setProperty('--mag-y', state.current.y.toFixed(2) + 'px');
  };

  const scheduleSmooth = (el, state) => {
    if (state.smoothFrame !== null) return;
    const step = () => {
      const dx = state.target.x - state.current.x;
      const dy = state.target.y - state.current.y;
      const easing = 0.2;

      state.current.x += dx * easing;
      state.current.y += dy * easing;
      applyStyles(el, state);

      if (Math.abs(dx) < 0.1 && Math.abs(dy) < 0.1) {
        state.current.x = state.target.x;
        state.current.y = state.target.y;
        applyStyles(el, state);
        state.smoothFrame = null;
        return;
      }

      state.smoothFrame = requestAnimationFrame(step);
    };
    state.smoothFrame = requestAnimationFrame(step);
  };

  const computeTarget = (el, state, clientX, clientY) => {
    const rect = el.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const dx = clientX - centerX;
    const dy = clientY - centerY;
    const distance = Math.hypot(dx, dy);

    if (distance > magnetSettings.radius) {
      state.target.x = 0;
      state.target.y = 0;
    } else {
      const normalized = 1 - distance / magnetSettings.radius;
      const pull = normalized * magnetSettings.strength;
      state.target.x = Math.max(Math.min(dx * pull, magnetSettings.maxOffset), -magnetSettings.maxOffset);
      state.target.y = Math.max(Math.min(dy * pull, magnetSettings.maxOffset), -magnetSettings.maxOffset);
    }

    scheduleSmooth(el, state);
  };

  if (icons.length) {
    window.addEventListener('pointermove', (event) => {
      icons.forEach((icon) => {
        const state = ensureState(icon);
        state.pending = { x: event.clientX, y: event.clientY };
        if (state.magnetFrame !== null) return;
        state.magnetFrame = requestAnimationFrame(() => {
          state.magnetFrame = null;
          if (!state.pending) return;
          computeTarget(icon, state, state.pending.x, state.pending.y);
          state.pending = null;
        });
      });
    }, { passive: true });

    window.addEventListener('pointerleave', () => {
      icons.forEach((icon) => {
        const state = ensureState(icon);
        state.target.x = 0;
        state.target.y = 0;
        scheduleSmooth(icon, state);
      });
    });
  }

  if (typeof window.ivRefreshGooButtons === 'function') {
    window.ivRefreshGooButtons();
  }

})();

// Wire the Login / Sign Up buttons (start page) to backend routes
(function () {
  try {
    const authSection = document.querySelector('.start-auth');
    if (!authSection) {
      return;
    }

    const authButtons = authSection.querySelectorAll('.goo-button');
    if (authButtons && authButtons.length >= 2) {
      const loginBtn = authButtons[0];
      const signupBtn = authButtons[1];
      loginBtn.addEventListener('click', () => { window.location.href = '/login'; });
      signupBtn.addEventListener('click', () => { window.location.href = '/signup'; });
    } else {
      // Fallback: detect by visible text within the auth section only
      authSection.querySelectorAll('.goo-button').forEach((btn) => {
        const txt = (btn.textContent || '').trim().toLowerCase();
        if (txt === 'login') btn.addEventListener('click', () => { window.location.href = '/login'; });
        if (txt === 'sign up' || txt === 'signup') btn.addEventListener('click', () => { window.location.href = '/signup'; });
      });
    }
  } catch (e) {
    // noop — keep page functional even if wiring fails
    console.warn('Auth button wiring failed', e);
  }
})();
