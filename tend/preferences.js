/* Preference fields share the same database-backed endpoint in both editions. */
(()=>{
  const $=selector=>document.querySelector(selector);
  async function api(method='GET',data){
    const response=await fetch('/api/preferences',{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});
    const result=await response.json();if(!response.ok)throw Error(result.detail||'Could not save reminder preferences');return result;
  }
  window.tetherLoadPreferences=async()=>{
    if(!$('#reminderPreferences'))return;
    try{const p=await api();$('#weekStart').value=String(p.week_start);$('#morningTime').value=p.morning_time;$('#nightTime').value=p.night_time}
    catch(error){$('#preferencesStatus').textContent=error.message}
  };
  document.addEventListener('DOMContentLoaded',()=>{
    const form=$('#reminderPreferences');if(!form)return;
    form.onsubmit=async event=>{
      event.preventDefault();const button=form.querySelector('button');button.disabled=true;
      try{await api('POST',{week_start:Number($('#weekStart').value),morning_time:$('#morningTime').value,night_time:$('#nightTime').value});$('#preferencesStatus').textContent='Reminder preferences saved.'}
      catch(error){$('#preferencesStatus').textContent=error.message}finally{button.disabled=false}
    };
  });
})();
