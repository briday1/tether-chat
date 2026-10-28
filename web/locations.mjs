/* Location lookup is a user-confirmed operation, never a model tool/network action. */
import {Problem,required,uid,copy} from './store.mjs';
export const SEARCH_URL='https://photon.komoot.io/api/';
export const mapsURL=query=>'https://www.google.com/maps/search/?'+new URLSearchParams({api:'1',query});
export function parsePlaces(data){
  if(!Array.isArray(data?.features))throw new Problem('Address search returned an invalid response. Try Google Maps below.');
  const results=[];
  for(const feature of data.features.slice(0,8)){
    if(!feature||typeof feature!=='object')continue;
    const p=feature.properties||{},[lon,lat]=feature.geometry?.coordinates||[];
    if(typeof lat!=='number'||typeof lon!=='number'||!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180)continue;
    const clean=value=>typeof value==='string'?value.trim().slice(0,200):'';
    const street=[clean(p.housenumber),clean(p.street)].filter(Boolean).join(' ');
    const parts=[clean(p.name),street,clean(p.city)||clean(p.town)||clean(p.village)||clean(p.district),clean(p.state),clean(p.postcode),clean(p.country)].filter(Boolean);
    const address=[...new Set(parts)].join(', ');if(!address)continue;
    const id=String(p.osm_type||'place')+':'+String(p.osm_id||lat+','+lon);
    if(results.some(r=>r.id===id))continue;
    results.push({id,address,lat,lon,maps_url:mapsURL(address),has_street:!!street});
  }
  return results;
}
export function locationRequests(m){return copy((m.s.location_requests||[]).filter(r=>m.s.tasks.some(t=>t.id===r.task_id&&!t.archived_at)).slice(-10).map(r=>({...r,task_title:m.task(r.task_id).title,maps_search_url:mapsURL(r.query)})))}
export function requestLocation(m,args){
  const task=m.task(args.id),query=required(args.query,'Place and town/city',500);
  if(task.archived_at)throw new Problem('Restore the task before adding its location');
  m.s.location_requests||=[];
  const existing=m.s.location_requests.find(r=>r.task_id===task.id&&r.query.toLowerCase()===query.toLowerCase());
  if(existing)return {...copy(existing),confirmation_required:existing.status==='pending'};
  const row={id:uid(),task_id:task.id,query,status:'pending',results:[],created_at:m.clock(),searched_at:null,saved_entry_id:null};
  m.s.location_requests.push(row);
  return {...copy(row),confirmation_required:true,message:'A confirmation card is ready. No address lookup has run. The user must confirm the place/city, search, and choose the correct result.'};
}
const target=(m,id)=>{const row=(m.s.location_requests||[]).find(r=>r.id===id);if(!row)throw new Problem('Location request not found',404);if(m.task(row.task_id).archived_at)throw new Problem('Task is archived');return row};
export function beginSearch(m,id,query){
  const row=target(m,id);query=required(query,'Place and town/city',500);
  if(row.status==='saved')throw new Problem('This location is already saved');
  const stamp=m.clock(),cached=(m.s.location_requests||[]).find(r=>r.query.toLowerCase()===query.toLowerCase()&&r.searched_at&&+new Date(stamp)-+new Date(r.searched_at)<86400000&&['ready','saved'].includes(r.status));
  if(cached){Object.assign(row,{query,status:'ready',results:copy(cached.results),searched_at:cached.searched_at,error:null});return {cached:true}}
  if(m.s.location_search_at&&+new Date(stamp)-+new Date(m.s.location_search_at)<2000)throw new Problem('Wait a moment before another address search',429);
  m.s.location_search_at=stamp;const token=uid();Object.assign(row,{query,status:'searching',search_token:token,error:null});return {token,query};
}
export function finishSearch(m,id,token,results,error=null){
  const row=target(m,id);if(row.search_token!==token)return copy(row);
  Object.assign(row,{status:error?'pending':'ready',results,error,searched_at:error?null:m.clock(),search_token:null});return copy(row);
}
const markdown=value=>value.replace(/[\\`*_{}\[\]()<>|]/g,'\\$&').replace(/[\r\n]+/g,' ');
export function saveLocation(m,id,resultId){
  const row=target(m,id);if(row.saved_entry_id)return {request:copy(row),entry:m.s.entries.find(e=>e.id===row.saved_entry_id)};
  const result=row.results.find(r=>r.id===resultId);if(row.status!=='ready'||!result)throw new Problem('Choose a result from the confirmed search');
  const body='Location: '+markdown(result.address)+'\n\n[Google Maps]('+result.maps_url+')\n\nAddress data: [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), via Photon. Selected by you.';
  const entry=m.add(row.task_id,'thought',body);Object.assign(row,{status:'saved',saved_entry_id:entry.id,selected:result});return {request:copy(row),entry};
}
