/* Homepage enhancement. Data comes exclusively from the existing Flask API. */
(() => {
  'use strict';
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const header = document.querySelector('.site-header');
  const menu = document.querySelector('.menu-toggle');
  const navigation = document.querySelector('.primary-nav');
  const hero = document.querySelector('.hero');
  const sky = document.querySelector('.hero-sky');
  const intro = document.querySelector('.hero-intro');

  function closeMenu(returnFocus = false) {
    navigation.classList.remove('is-open');
    menu.setAttribute('aria-expanded', 'false');
    menu.querySelector('span').textContent = 'Menu';
    if (returnFocus) menu.focus();
  }
  menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    menu.querySelector('span').textContent = open ? 'Close' : 'Menu';
    navigation.classList.toggle('is-open', open);
  });
  navigation.addEventListener('click', event => {
    if (event.target.closest('a')) closeMenu();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') closeMenu(true);
  });
  document.addEventListener('click', event => {
    if (!header.contains(event.target)) closeMenu();
  });
  const mobile = window.matchMedia('(max-width: 700px)');
  mobile.addEventListener('change', () => closeMenu());

  // Normal browser scrolling, batched into one animation frame; no scroll hijack.
  let scheduled = false;
  function updateScroll() {
    const y = window.scrollY;
    header.classList.toggle('is-scrolled', y > 30);
    if (!reducedMotion.matches && y < hero.offsetHeight) {
      sky.style.transform = `translateY(${Math.min(y * 0.18, 150)}px)`;
      intro.style.transform = `translateY(${-Math.min(y * 0.13, 90)}px)`;
      intro.style.opacity = String(Math.max(0, 1 - y / 550));
    }
    scheduled = false;
  }
  window.addEventListener('scroll', () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(updateScroll); }
  }, { passive: true });
  updateScroll();

  if ('IntersectionObserver' in window && !reducedMotion.matches) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    document.documentElement.classList.add('motion-ready');
    document.querySelectorAll('.reveal').forEach(element => observer.observe(element));
  }
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) {
      document.documentElement.classList.remove('motion-ready');
      sky.style.removeProperty('transform');
      intro.style.removeProperty('transform');
      intro.style.removeProperty('opacity');
    }
    updateScroll();
  });

  // Only the homepage is implemented at this checkpoint. Future page actions
  // explain availability rather than opening dead links or simulated workflows.
  const dialog = document.querySelector('#feature-preview');
  const previewTitle = document.querySelector('#preview-title');
  const previewDescription = document.querySelector('#preview-description');
  const previewLink = dialog.querySelector('[data-close-dialog]');
  let opener = null;
  document.querySelectorAll('[data-preview]').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault();
      opener = link;
      const archive = link.dataset.preview === 'archive';
      previewTitle.textContent = archive ? 'A universe to explore.' : 'Follow the signal.';
      previewDescription.textContent = archive
        ? 'The searchable catalog is coming next. The archive counts on this homepage are already drawn from the real local NASA Kepler dataset.'
        : 'The prediction experience is coming next. For now, discover how Kepler observations become model classifications.';
      previewLink.href = archive ? '#archive' : '#method';
      previewLink.firstChild.textContent = archive ? 'Return to the archive ' : 'Discover the process ';
      closeMenu();
      dialog.showModal();
      document.body.classList.add('modal-open');
    });
  });
  dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  previewLink.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
  });
  dialog.addEventListener('close', () => {
    document.body.classList.remove('modal-open');
    if (opener && opener.getClientRects().length) opener.focus({ preventScroll: true });
    else if (mobile.matches) menu.focus({ preventScroll: true });
  });

  const statsSection = document.querySelector('#archive');
  const grid = document.querySelector('.stats-grid');
  const status = document.querySelector('#stats-status');
  const retry = document.querySelector('#retry-stats');
  const fields = [...document.querySelectorAll('[data-stat]')];
  const formatter = new Intl.NumberFormat('en-US');
  async function loadStatistics() {
    grid.setAttribute('aria-busy', 'true');
    retry.hidden = true;
    status.textContent = 'Loading the local Kepler catalog…';
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(statsSection.dataset.statsUrl, { headers: { Accept: 'application/json' }, signal: controller.signal });
      if (!response.ok) throw new Error('Catalog unavailable');
      const data = await response.json();
      if (!data.success || fields.some(field => !Number.isSafeInteger(data[field.dataset.stat]) || data[field.dataset.stat] < 0)) throw new Error('Invalid catalog response');
      // Keep exact catalog counts readable; avoid transient, misleading totals.
      fields.forEach(field => { field.textContent = formatter.format(data[field.dataset.stat]); });
      status.textContent = 'NASA KEPLER OBJECTS OF INTEREST · LOCAL CATALOG';
    } catch (error) {
      fields.forEach(field => { field.textContent = '—'; });
      status.textContent = 'The catalog is temporarily unavailable. Please try again.';
      retry.hidden = false;
    } finally {
      window.clearTimeout(timeout);
      grid.setAttribute('aria-busy', 'false');
    }
  }
  retry.addEventListener('click', loadStatistics);
  loadStatistics();
})();
