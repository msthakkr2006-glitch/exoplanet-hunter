(() => {
  'use strict';
  const {request,el,number,badge}=window.EH;
  const form=document.querySelector('#search-form'), search=document.querySelector('#catalog-search');
  const rows=document.querySelector('#catalog-rows'), status=document.querySelector('#catalog-status');
  const errorBox=document.querySelector('#catalog-error'), empty=document.querySelector('#catalog-empty');
  const prev=document.querySelector('#previous-page'), next=document.querySelector('#next-page');
  const detail=document.querySelector('#observation-detail'), placeholder=document.querySelector('#detail-placeholder');
  const detailError=document.querySelector('#detail-error'), detailPanel=document.querySelector('.observation-panel');
  const parameters=new URLSearchParams(location.search);
  let page=/^[1-9]\d{0,6}$/.test(parameters.get('page') || '') ? Number(parameters.get('page')) : 1;
  let query=(parameters.get('q') || '').slice(0,200), selected='', listController, detailController;
  search.value=query;
  function clearDetail() { detailController?.abort(); selected=''; detail.hidden=true; detailError.hidden=true; placeholder.hidden=false; placeholder.querySelector('h2').textContent='Select a signal'; placeholder.querySelector('p').textContent='Choose an observation to explore its measurements and catalog disposition.'; detailPanel.setAttribute('aria-busy','false'); }
  async function selectObject(id) {
    detailController?.abort(); const controller=new AbortController(); detailController=controller; selected=id;
    rows.querySelectorAll('tr').forEach(row => {const chosen=row.dataset.id===id;row.classList.toggle('is-selected',chosen);row.querySelector('button').setAttribute('aria-pressed',String(chosen));});
    detail.hidden=true; detailError.hidden=true; placeholder.hidden=false;
    placeholder.querySelector('h2').textContent='Reading the signal…'; placeholder.querySelector('p').textContent=id;
    detailPanel.setAttribute('aria-busy','true');
    try {
      const {object}=await request(`/api/objects/${encodeURIComponent(id)}`,{signal:controller.signal});
      if(controller!==detailController) return;
      document.querySelector('#object-name').textContent=object.object_id;
      document.querySelector('#object-alias').textContent=[object.identifiers.kepler_name,`Host star ${object.identifiers.kepid ?? 'unavailable'}`].filter(Boolean).join(' · ');
      const old=document.querySelector('#object-disposition'), label=badge(object.nasa_disposition); label.id=old.id; old.replaceWith(label);
      const list=document.querySelector('#object-measurements'); list.replaceChildren();
      const measurements=[['koi_period','Orbital period','days'],['koi_prad','Planet radius','R⊕'],['koi_teq','Equilibrium temp.','K'],['koi_depth','Transit depth','ppm'],['koi_steff','Stellar temperature','K'],['koi_srad','Stellar radius','R☉'],['koi_duration','Transit duration','hours'],['koi_model_snr','Signal-to-noise','']];
      measurements.forEach(([key,title,unit]) => {const wrapper=el('div'), value=el('dd',number(object.features[key],key==='koi_period'?5:2)); if(object.features[key]!==null) value.append(el('small',` ${unit}`)); wrapper.append(el('dt',title),value); list.append(wrapper);});
      const missing=Object.values(object.features).filter(v=>v===null).length;
      document.querySelector('#object-missing').textContent=missing ? `${missing} unavailable measurement${missing===1?'':'s'}. The saved imputer can handle partial missing values.` : 'All ten model measurements are available.';
      document.querySelector('#analyze-object').href=`/predict?object_id=${encodeURIComponent(object.object_id)}`;
      placeholder.hidden=true; detail.hidden=false;
    } catch(error) {
      if(controller!==detailController || error.name==='AbortError') return;
      placeholder.hidden=true; detailError.hidden=false; detailError.querySelector('p').textContent=error.message;
    } finally { if(controller===detailController) detailPanel.setAttribute('aria-busy','false'); }
  }
  async function load() {
    listController?.abort(); const controller=new AbortController(); listController=controller;
    clearDetail(); rows.replaceChildren(); errorBox.hidden=true; empty.hidden=true; prev.disabled=true; next.disabled=true;
    status.textContent='Loading the archive…'; rows.closest('section').setAttribute('aria-busy','true');
    document.querySelector('#page-status').textContent='Page —'; document.querySelector('#clear-search').hidden=!query;
    const params=new URLSearchParams({page:String(page),per_page:'8'}); if(query) params.set('q',query);
    const address=new URLSearchParams(); if(query) address.set('q',query); if(page>1) address.set('page',String(page));
    history.replaceState(null,'',`${location.pathname}${address.size?'?'+address:''}`);
    try {
      const data=await request(`/api/objects?${params}`,{signal:controller.signal}); if(controller!==listController) return;
      const p=data.pagination;
      status.textContent=`${number(p.total,0)} observation${p.total===1?'':'s'}${query?' matching your search':' in the local catalog'}`;
      data.objects.forEach(object => {
        const row=el('tr'); row.dataset.id=object.object_id;
        [object.object_id,number(object.features.koi_period,4),number(object.features.koi_prad),number(object.features.koi_model_snr,1)].forEach(text=>row.append(el('td',text)));
        const disposition=el('td'); disposition.append(badge(object.nasa_disposition)); row.append(disposition);
        const action=el('td'), button=el('button','Details →','row-detail'); button.type='button'; button.setAttribute('aria-label',`Details for ${object.object_id}`); button.setAttribute('aria-pressed','false'); button.addEventListener('click',()=>selectObject(object.object_id)); action.append(button); row.append(action); rows.append(row);
      });
      empty.hidden=data.objects.length>0;
      if(!data.objects.length && p.total>0) empty.querySelector('p').textContent='This page is beyond the matching records. Use Previous or start a new search.';
      else empty.querySelector('p').textContent='Try a KOI name such as K00752.01, a Kepler name, or a host-star ID.';
      document.querySelector('#page-status').textContent=p.total_pages ? `Page ${page} of ${number(p.total_pages,0)}` : 'No results';
      prev.disabled=!p.has_previous; next.disabled=!p.has_next;
      if(data.objects.length) selectObject(data.objects[0].object_id);
    } catch(error) {
      if(controller!==listController || error.name==='AbortError') return;
      status.textContent='The archive could not be loaded.'; errorBox.hidden=false; errorBox.querySelector('p').textContent=error.message;
    } finally { if(controller===listController) rows.closest('section').setAttribute('aria-busy','false'); }
  }
  form.addEventListener('submit',e=>{e.preventDefault();query=search.value.trim();page=1;load();});
  document.querySelector('#clear-search').addEventListener('click',()=>{query='';search.value='';page=1;load();});
  prev.addEventListener('click',()=>{if(page>1){page--;load();}}); next.addEventListener('click',()=>{page++;load();});
  document.querySelector('#catalog-retry').addEventListener('click',load);
  document.querySelector('#detail-retry').addEventListener('click',()=>selectObject(selected));
  load();
})();
