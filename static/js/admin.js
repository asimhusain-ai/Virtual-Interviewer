(function () {
  const layout = document.querySelector('[data-admin-layout]');
  const sidebar = document.querySelector('[data-admin-sidebar]');
  const toggle = document.querySelector('[data-admin-nav-toggle]');
  const overlay = document.querySelector('[data-admin-nav-overlay]');
  if (!layout || !sidebar || !toggle || !overlay) {
    return;
  }

  const OPEN_CLASS = 'admin-sidebar-open';
  const BODY_LOCK = 'admin-scroll-lock';
  const body = document.body;

  const closeSidebar = () => {
    layout.classList.remove(OPEN_CLASS);
    overlay.classList.remove('visible');
    toggle.setAttribute('aria-expanded', 'false');
    body.classList.remove(BODY_LOCK);
  };

  const openSidebar = () => {
    layout.classList.add(OPEN_CLASS);
    overlay.classList.add('visible');
    toggle.setAttribute('aria-expanded', 'true');
    body.classList.add(BODY_LOCK);
  };

  const toggleSidebar = () => {
    if (layout.classList.contains(OPEN_CLASS)) {
      closeSidebar();
    } else {
      openSidebar();
    }
  };

  toggle.addEventListener('click', toggleSidebar);
  overlay.addEventListener('click', closeSidebar);
  document.addEventListener('keyup', (event) => {
    if (event.key === 'Escape') {
      closeSidebar();
    }
  });

  const navLinks = sidebar.querySelectorAll('a');
  navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      if (window.matchMedia('(max-width: 960px)').matches) {
        closeSidebar();
      }
    });
  });

  const syncStateForViewport = () => {
    if (!window.matchMedia('(max-width: 960px)').matches) {
      layout.classList.remove(OPEN_CLASS);
      overlay.classList.remove('visible');
      toggle.setAttribute('aria-expanded', 'false');
      body.classList.remove(BODY_LOCK);
    }
  };

  window.addEventListener('resize', syncStateForViewport);
  syncStateForViewport();
})();
