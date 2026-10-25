(() => {
  'use strict';
  const {request,el}=window.EH;
  const form=document.querySelector('#prediction-form'), inputs=[...form.querySelectorAll('input[name]')];
  const loader=document.querySelector('#observation-loader'), idInput=document.querySelector('#observation-id');
  const sourceStatus=document.querySelector('#source-status'), sourceError=document.querySelector('#source-error');
  const choices=document.querySelector('#ambiguous-objects'), formError=document.querySelector('#form-error');
  const submit=document.querySelector('#classify-button'), resultPanel=document.querySelector('.result-panel');
  const heading=document.querySelector('#result-heading'), explanation=document.querySelector('#result-explanation');
  let source=null, edited=false, loadController=null, predictionController=null;
  function setBusy(busy) {
    submit.disabled=busy; resultPanel.setAttribute('aria-busy',String(busy));
    submit.firstChild.textContent=busy ? 'Classifying… ' : 'Classify Observation ';
  }
  function clearErrors() {
    formError.hidden=true; formError.textContent='';
    inputs.forEach(input=>{input.removeAttribute('aria-invalid');document.querySelector(`#error-${input.name}`).textContent='';});
  }
  function invalidate() {
    predictionController?.abort(); predictionController=null; setBusy(false);
    document.querySelector('#score-result').hidden=true;
    document.querySelector('#result-kicker').textContent='AWAITING CLASSIFICATION';
    heading.textContent='What does the signal suggest?';
    explanation.textContent='Classify the current measurements to see a model interpretation.';
  }
  function updateSource() {
    sourceStatus.textContent=source
      ? `${source.object_id}${source.identifiers.kepler_name?' · '+source.identifiers.kepler_name:''} · NASA catalog: ${source.nasa_disposition || 'unavailable'}.${edited?' Measurements edited; the catalog label describes the original observation.':''}`
      : 'Enter measurements below. Leave unavailable values blank to use the saved median imputer.';
  }
  function setObjectUrl(id) { const url=new URL(location.href); if(id) url.searchParams.set('object_id',id); else url.searchParams.delete('object_id'); history.replaceState(null,'',url.pathname+url.search); }
  function fieldError(input,message) {input.setAttribute('aria-invalid','true');document.querySelector(`#error-${input.name}`).textContent=message;}

  async function loadObservation(id) {
    loadController?.abort(); const controller=new AbortController(); loadController=controller;
    invalidate(); clearErrors(); source=null; edited=false; inputs.forEach(input=>{input.value='';input.disabled=true;});
    sourceError.hidden=true; choices.hidden=true; choices.replaceChildren(); sourceStatus.textContent='Loading the observation’s actual measurements…';
    loader.querySelector('button').disabled=true; submit.disabled=true;
    try {
      const data=await request(`/api/objects/${encodeURIComponent(id)}`,{signal:controller.signal});
      if(controller!==loadController) return;
      source=data.object;
      inputs.forEach(input=>{const value=source.features[input.name]; input.value=value===null || value===undefined ? '' : String(value);});
      idInput.value=source.object_id; setObjectUrl(source.object_id); updateSource();
    } catch(error) {
      if(controller!==loadController || error.name==='AbortError') return;
      sourceStatus.textContent='No observation loaded. Enter a unique KOI identifier or switch to manual input.';
      sourceError.hidden=false; sourceError.textContent=error.message; setObjectUrl(null);
      if(error.status===409 && Array.isArray(error.details?.object_ids)) {
        choices.hidden=false;
        error.details.object_ids.forEach(id=>{const button=el('button',id);button.type='button';button.addEventListener('click',()=>loadObservation(id));choices.append(button);});
      }
    } finally {
      if(controller===loadController) {inputs.forEach(input=>{input.disabled=false;});loader.querySelector('button').disabled=false;submit.disabled=false;loadController=null;}
    }
  }
  document.querySelectorAll('[name="input-mode"]').forEach(radio=>radio.addEventListener('change',()=>{
    const catalog=radio.value==='catalog'; loader.hidden=!catalog;
    if(!catalog) {
      loadController?.abort(); loadController=null; inputs.forEach(input=>{input.disabled=false;}); loader.querySelector('button').disabled=false;
      source=null; edited=false; sourceError.hidden=true; choices.hidden=true; setObjectUrl(null); updateSource(); invalidate();
    } else idInput.focus();
  }));
  loader.addEventListener('submit',event=>{event.preventDefault(); const id=idInput.value.trim(); if(id) loadObservation(id);});
  inputs.forEach(input=>input.addEventListener('input',()=>{edited=Boolean(source);clearErrors();invalidate();updateSource();}));
  document.querySelector('#clear-measurements').addEventListener('click',()=>{
    loadController?.abort();loadController=null;inputs.forEach(input=>{input.value='';input.disabled=false;});loader.querySelector('button').disabled=false;
    source=null;edited=false;sourceError.hidden=true;choices.hidden=true;setObjectUrl(null);updateSource();clearErrors();invalidate();inputs[0].focus();
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault(); if(loadController || predictionController) return;
    clearErrors(); const payload={}; let invalid=null;
    inputs.forEach(input=>{
      let message='';
      if(input.validity.badInput) message='Enter a finite number, or leave the field blank.';
      else if(input.value.trim()==='') payload[input.name]=null;
      else {
        const value=input.valueAsNumber;
        if(!Number.isFinite(value)) message='Enter a finite number.';
        else if(value<0 || (input.dataset.positive==='true' && value===0)) message=input.dataset.positive==='true'?'Must be greater than zero.':'Must be nonnegative.';
        else payload[input.name]=value;
      }
      if(message){fieldError(input,message);invalid ||= input;}
    });
    if(invalid){formError.hidden=false;formError.textContent='Please correct the highlighted measurements.';invalid.focus();return;}
    if(Object.values(payload).every(value=>value===null)){formError.hidden=false;formError.textContent='Enter at least one measured feature. An entirely blank observation cannot be classified.';inputs[0].focus();return;}
    invalidate(); const controller=new AbortController();predictionController=controller;setBusy(true);
    document.querySelector('#result-kicker').textContent='READING THE PATTERNS';heading.textContent='Classifying…';
    explanation.textContent='The saved Random Forest pipeline is evaluating these measurements.';
    try {
      const result=await request('/api/predict',{method:'POST',body:JSON.stringify(payload),signal:controller.signal});
      if(controller!==predictionController) return;
      if(![0,1].includes(result.prediction) || typeof result.planet_like_score!=='number' || !Number.isFinite(result.planet_like_score) || result.planet_like_score<0 || result.planet_like_score>1) throw new Error('The model returned an invalid result. Please retry.');
      document.querySelector('#result-kicker').textContent='MODEL CLASSIFICATION';heading.textContent=result.classification;
      explanation.textContent=result.prediction===1
        ? 'The model identifies patterns in these measurements that resemble observations labeled planet-like in its training data.'
        : 'The model favors a false-positive classification. The measurements more closely resemble false-positive observations in its training data.';
      const percent=result.planet_like_score*100;
      document.querySelector('#score-number').textContent=`${percent.toFixed(1)}%`;
      const meter=document.querySelector('#score-meter');meter.setAttribute('aria-valuenow',String(percent));meter.querySelector('span').style.width=`${percent}%`;
      document.querySelector('#score-result').hidden=false;
      const imputed=result.imputed_features || [];
      document.querySelector('#imputed-note').textContent=imputed.length ? `Saved training medians used for: ${imputed.map(name=>form.querySelector(`label[for="${name}"]`).childNodes[0].textContent.trim()).join(', ')}.` : 'All ten measurements were supplied; no imputation was needed.';
      document.querySelector('#prediction-source').textContent=source ? `${edited?'Edited measurements based on':'Source'} ${source.object_id} · NASA catalog: ${source.nasa_disposition || 'unavailable'}. The catalog disposition is not the model prediction.` : 'Source: manually supplied measurements.';
    } catch(error) {
      if(controller!==predictionController || error.name==='AbortError') return;
      formError.hidden=false;formError.textContent=error.message;
      if(error.details && typeof error.details==='object') inputs.forEach(input=>{if(typeof error.details[input.name]==='string') fieldError(input,error.details[input.name]);});
      document.querySelector('#result-kicker').textContent='CLASSIFICATION UNAVAILABLE';heading.textContent='Unable to classify';explanation.textContent='Review the measurements or try again. No model result is being displayed.';
    } finally {if(controller===predictionController){predictionController=null;setBusy(false);}}
  });
  const selectedId=new URLSearchParams(location.search).get('object_id');
  if(selectedId){document.querySelector('[name="input-mode"][value="catalog"]').checked=true;loader.hidden=false;idInput.value=selectedId.slice(0,200);loadObservation(idInput.value);}
})();
