/* Shared interior-page UI and API helpers; never loaded on the homepage. */
(() => {
  'use strict';
  const header = document.querySelector('.site-header');
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.primary-nav');
  function closeMenu(focus = false) {
    nav.classList.remove('is-open'); menu.setAttribute('aria-expanded', 'false');
    menu.querySelector('span').textContent = 'Menu'; if (focus) menu.focus();
  }
  menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open)); nav.classList.toggle('is-open', open);
    menu.querySelector('span').textContent = open ? 'Close' : 'Menu';
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && nav.classList.contains('is-open')) closeMenu(true); });
  document.addEventListener('click', e => { if (!header.contains(e.target)) closeMenu(); });
  nav.addEventListener('click', e => { if (e.target.closest('a')) closeMenu(); });
  matchMedia('(max-width:700px)').addEventListener('change', () => closeMenu());
  const updateHeader = () => header.classList.toggle('is-scrolled', scrollY > 30);
  addEventListener('scroll', updateHeader, {passive:true}); updateHeader();

  async function request(url, options = {}) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (options.signal?.aborted) cancel();
    options.signal?.addEventListener('abort', cancel, {once:true});
    const timer = setTimeout(cancel, 15000);
    try {
      const response = await fetch(url, {...options, signal:controller.signal, headers:{Accept:'application/json', ...(options.body ? {'Content-Type':'application/json'} : {}), ...options.headers}});
      const data = await response.json();
      if (!response.ok || data.success === false) {
        const error = new Error(data.error?.message || 'This request could not be completed.');
        error.status = response.status; error.details = data.error?.details; throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') {
        if (options.signal?.aborted) throw error;
        throw new Error('The request timed out. Please try again.');
      }
      if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('Unable to reach the local catalog service. Please try again.');
      throw error;
    } finally {
      clearTimeout(timer); options.signal?.removeEventListener('abort', cancel);
    }
  }
  function el(tag, text = '', cls = '') { const node=document.createElement(tag); node.textContent=text; if(cls) node.className=cls; return node; }
  function number(value, digits=2) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-US',{maximumFractionDigits:digits}); }
  function badge(disposition) { const tag=el('span',disposition || 'UNAVAILABLE','badge'); tag.classList.add(disposition === 'CONFIRMED' ? 'confirmed' : disposition === 'CANDIDATE' ? 'candidate' : 'false-positive'); return tag; }
  window.EH = {request, el, number, badge};
})();
