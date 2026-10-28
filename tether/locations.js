/* A real click confirms each external lookup; the assistant only prepares cards. */
(() => {
 const cards=new Map();
 const element=(tag,text)=>{const node=document.createElement(tag);if(text)node.textContent=text;return node};
 const link=(text,url)=>{const node=element('a',text);node.href=url;node.target='_blank';node.rel='noopener noreferrer';return node};
 async function post(path,body){const response=await fetch('/api/locations/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.detail||'The location could not be saved');return result}
 window.tetherLocationCards=rows=>(rows||[]).map(row=>{
  let card=cards.get(row.id);if(!card){card=element('section');card.className='bubble assistant location-card';card.dataset.locationId=row.id;cards.set(row.id,card)}
  const signature=JSON.stringify([row.status,row.query,row.results,row.error,row.selected]);if(card.dataset.signature===signature)return card;
  card.dataset.signature=signature;card.replaceChildren();
  card.append(element('p','Location for '+row.task_title));
  if(row.status==='saved'){
   card.append(element('p',row.selected.address),link('Open in Google Maps',row.selected.maps_url),element('small','Saved with the task.'));return card;
  }
  const label=element('label','Place and town/city');const input=element('input');input.value=row.query;input.maxLength=500;label.append(input);
  const status=element('p',row.error||'Confirm the place and city, then choose the correct result.');status.setAttribute('role','status');
  const button=element('button','Confirm and find address');button.type='button';
  const fallback=link('Search Google Maps',row.maps_search_url);
  input.oninput=()=>{fallback.href='https://www.google.com/maps/search/?'+new URLSearchParams({api:'1',query:input.value})};
  button.onclick=async()=>{button.disabled=true;input.disabled=true;status.textContent='Finding addresses…';try{
    const next=await post(row.id+'/search',{query:input.value});next.task_title=row.task_title;next.maps_search_url=fallback.href;window.tetherLocationCards([next]);
   }catch(error){status.textContent=error.message}finally{button.disabled=false;input.disabled=false}};
  card.append(label,status,button,fallback);
  if(row.status==='ready'){
   if(!row.results.length)card.append(element('p','No matching address found. Add a town/city or try Google Maps.'));
   for(const result of row.results){
    const option=element('div');option.className='location-result';option.append(element('p',result.address),link('View in Google Maps',result.maps_url));
    const select=element('button','Use this location');select.type='button';select.onclick=async()=>{
     select.disabled=true;try{const saved=await post(row.id+'/save',{result_id:result.id});window.tetherLocationCards([{...saved.request,task_title:row.task_title}]);window.dispatchEvent(new Event('tether-data-changed'))}catch(error){status.textContent=error.message;select.disabled=false}
    };option.append(select);card.append(option);
   }
  }
  const attribution=element('small');attribution.append(document.createTextNode('Search: Photon · '),link('© OpenStreetMap contributors','https://www.openstreetmap.org/copyright'));card.append(attribution);
  return card;
 });
})();
