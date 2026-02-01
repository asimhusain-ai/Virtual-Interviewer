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

  if (typeof window.ivRefreshGooButtons === 'function') {
    window.ivRefreshGooButtons();
  }

  const ambientImages = Array.from(document.querySelectorAll('.ambient-cluster img'));
  if (ambientImages.length) {
    const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!prefersReduced) {
      const shuffle = (arr) => {
        for (let i = arr.length - 1; i > 0; i -= 1) {
          const j = Math.floor(Math.random() * (i + 1));
          [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
      };

      let order = shuffle(ambientImages.slice());
      let index = 0;
      let active = null;
      const displayMs = 5000;
      const fadeOutLeadMs = 1000;

      const showNext = () => {
        if (index >= order.length) {
          order = shuffle(ambientImages.slice());
          index = 0;
        }
        active = order[index];
        index += 1;
        active.classList.add('ambient-active');

        setTimeout(() => {
          active?.classList.remove('ambient-active');
        }, Math.max(0, displayMs - fadeOutLeadMs));

        setTimeout(() => {
          showNext();
        }, displayMs);
      };

      const startCycle = () => {
        showNext();
      };

      const waitForReady = () => {
        if (!document.body.classList.contains('heading-anim-init')) {
          startCycle();
          return;
        }
        requestAnimationFrame(waitForReady);
      };

      if (document.readyState === 'complete') {
        waitForReady();
      } else {
        window.addEventListener('load', () => {
          waitForReady();
        }, { once: true });
      }
    }
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
