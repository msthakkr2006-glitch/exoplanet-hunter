(() => {
  'use strict';
  const status=document.querySelector('#model-status'), retry=document.querySelector('#model-retry');
  async function load() {
    retry.hidden=true;status.textContent='Loading documented model metadata…';
    try {
      const data=await window.EH.request('/api/model/info'), values=data.historical_evaluation;
      for(const node of document.querySelectorAll('[data-model-metric]')) {
        const key=node.dataset.modelMetric,value=values?.[key];
        if(typeof value!=='number' || !Number.isFinite(value)) throw new Error('Historical model metrics are unavailable.');
        node.textContent=key==='test_accuracy' ? `${(value*100).toFixed(2)}%` : key==='test_weighted_f1' ? `≈ ${value.toFixed(2)}` : value.toFixed(4);
      }
      status.textContent=`Historical metadata from the saved-model API; not recalculated here. ${data.model_loaded?'The saved model is available for inference.':'The saved model is currently unavailable for inference.'}`;
    } catch(error) {
      document.querySelectorAll('[data-model-metric]').forEach(node=>{node.textContent='—';});
      status.textContent=error.message;retry.hidden=false;
    }
  }
  retry.addEventListener('click',load);load();
})();
