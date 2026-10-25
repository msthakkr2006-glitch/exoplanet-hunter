(() => {
  'use strict';
  const {request,number}=window.EH;
  const dataStatus=document.querySelector('#about-data-status'),dataRetry=document.querySelector('#about-data-retry');
  const modelStatus=document.querySelector('#about-model-status'),modelRetry=document.querySelector('#about-model-retry');
  async function loadData() {
    dataRetry.hidden=true;dataStatus.textContent='Loading the local catalog counts…';
    try {
      const data=await request('/api/stats');
      document.querySelectorAll('[data-about-stat]').forEach(node=>{const value=data[node.dataset.aboutStat];if(!Number.isSafeInteger(value)||value<0) throw new Error('Catalog counts are unavailable.');node.textContent=number(value,0);});
      dataStatus.textContent='Counts calculated from the local NASA Kepler catalog.';
    } catch(error) {document.querySelectorAll('[data-about-stat]').forEach(node=>{node.textContent='—';});dataStatus.textContent=error.message;dataRetry.hidden=false;}
  }
  async function loadModel() {
    modelRetry.hidden=true;modelStatus.textContent='Loading historical model performance…';
    try {
      const data=await request('/api/model/info'),m=data.historical_evaluation;
      if(typeof m?.test_accuracy!=='number'||typeof m?.test_roc_auc!=='number')throw new Error('Model metadata is unavailable.');
      modelStatus.textContent=`Historical final test results: ${(m.test_accuracy*100).toFixed(2)}% accuracy · ${m.test_roc_auc.toFixed(4)} ROC-AUC. Recorded experimental results, not a new evaluation.`;
    }catch(error){modelStatus.textContent=error.message;modelRetry.hidden=false;}
  }
  dataRetry.addEventListener('click',loadData);modelRetry.addEventListener('click',loadModel);loadData();loadModel();
})();

/* Reveal the personal chapter once, with a fully visible no-script fallback. */
(() => {
  'use strict';
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const elements = [...document.querySelectorAll('[data-developer-reveal]')];
  if (motion.matches || !('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.remove('developer-pending');
        observer.unobserve(entry.target);
      }
    });
  }, {threshold: .08});
  elements.forEach(element => {
    if (element.getBoundingClientRect().top > innerHeight) element.classList.add('developer-pending');
    observer.observe(element);
  });
  motion.addEventListener('change', event => {
    if (event.matches) {
      observer.disconnect();
      elements.forEach(element => element.classList.remove('developer-pending'));
    }
  });
})();
