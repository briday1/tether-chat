/* Click to dictate into an editable draft; click again to keep it. Never auto-send. */
(() => {
  const engineURL=new URL('speech.mjs',document.currentScript.src);
  const release=new URL(document.currentScript.src).searchParams.get('release');
  if(release)engineURL.searchParams.set('release',release);
  function init(){
    const input=document.querySelector('#message'),form=document.querySelector('#composer');if(!input||!form)return;
    const namespace=window.TETHER_CONFIG?'tether-web:'+window.TETHER_CONFIG.base:'tether-desktop:'+location.port;
    const preferenceKey=namespace+':voice';let prefs={mode:'local',language:navigator.language||'en-US'};
    try{prefs={...prefs,...JSON.parse(localStorage.getItem(preferenceKey)||'{}')}}catch(_){}
    // Upgrade Automatic/Provider preferences to local speech, including providers without an audio API.
    if(prefs.mode!=='browser')prefs.mode='local';
    const make=(tag,cls)=>{const node=document.createElement(tag);node.className=cls;return node};
    const mic=make('button','voice-button'),cancel=make('button','voice-button voice-cancel'),status=make('div','voice-status');
    mic.type=cancel.type='button';mic.id='voiceInput';cancel.id='voiceCancel';status.id='voiceStatus';
    status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    mic.innerHTML='<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>';
    cancel.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
    cancel.title='Discard this dictation';cancel.setAttribute('aria-label','Cancel voice input');
    const send=document.querySelector('#send');send.before(mic,cancel);form.append(status);
    let phase='idle',recognizer=null,session=null,generation=0,original='',acceptResults=false,settingInput=false,timer;
    const say=text=>{status.textContent=text};
    function refresh(){
      const active=phase!=='idle';mic.classList.toggle('listening',phase==='listening');
      mic.setAttribute('aria-pressed',String(active));mic.setAttribute('aria-busy',String(phase==='starting'||phase==='stopping'));
      mic.title=active?'Stop voice input':'Start voice input';mic.setAttribute('aria-label',mic.title);
      cancel.hidden=!active;send.disabled=active;
    }
    function writeDraft(text){settingInput=true;input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));settingInput=false}
    function transcript(text){if(!acceptResults)return;writeDraft(original+(original&&text&&!/\s$/.test(original)?' ':'')+text)}
    function idle(){clearTimeout(timer);phase='idle';session=null;recognizer=null;refresh()}
    function cancelVoice(restore=true){
      generation++;const shouldRestore=restore&&acceptResults;acceptResults=false;
      session?.cancel();try{recognizer?.abort()}catch(_){}
      if(shouldRestore)writeDraft(original);idle();say('Dictation discarded.');
    }
    function errorMessage(error){
      if(error.name==='NotAllowedError')return 'Microphone access was denied. Allow it in your browser or system settings.';
      if(error.name==='NotFoundError')return 'No microphone was found. Check its connection and try again.';
      if(error.name==='NotReadableError')return 'The microphone is in use or unavailable. Close other recording apps and try again.';
      return error.message||'On-device speech could not start. Check internet access for the first download, then try again.';
    }
    async function stopVoice(){
      if(phase==='idle'||phase==='stopping')return;
      if(phase==='starting'){cancelVoice(false);say('Voice input stopped.');return}
      phase='stopping';refresh();say('Finishing dictation…');
      if(recognizer){try{recognizer.stop()}catch(_){idle()}return}
      const token=generation;
      try{await session?.stop()}finally{
        if(token===generation){acceptResults=false;idle();say('Dictation stopped. Review your message before sending.');input.focus()}
      }
    }
    function browserSpeech(token){
      const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition;
      if(!Constructor)throw Error('Browser dictation is unavailable here. Choose On-device speech in Settings.');
      recognizer=new Constructor();recognizer.lang=prefs.language;recognizer.continuous=true;recognizer.interimResults=true;
      recognizer.onstart=()=>{if(token!==generation)return;phase='listening';refresh();say('Listening… Click the microphone again to stop.')};
      recognizer.onresult=event=>{if(token===generation)transcript(Array.from(event.results).map(result=>result[0]?.transcript||'').join(' ').trim())};
      let failed=false;
      recognizer.onerror=event=>{
        if(token!==generation)return;failed=true;acceptResults=false;
        if(['not-allowed','service-not-allowed'].includes(event.error))say('Microphone or speech access was denied. Allow it in browser or system settings.');
        else if(event.error==='no-speech')say('No speech was detected.');
        else if(event.error==='audio-capture')say('No microphone is available. Check its connection and permissions.');
        else say('Browser dictation is unavailable. Choose On-device speech in Settings; it uses no provider audio API.');
      };
      recognizer.onend=()=>{if(token!==generation)return;acceptResults=false;idle();if(!failed)say('Dictation stopped. Review your message before sending.')};
      recognizer.start();
    }
    async function startVoice(){
      const token=++generation;original=input.value;acceptResults=true;phase='starting';refresh();say('Opening microphone…');
      try{
        if(prefs.mode==='browser'){browserSpeech(token);return}
        const engine=await import(engineURL.href);if(token!==generation)return;
        session=engine.localSpeech({
          onText:text=>{if(token===generation)transcript(text)},
          onStatus:text=>{if(token!==generation)return;if(text.startsWith('Listening')){phase='listening';refresh()}say(text)},
          onError:error=>{if(token!==generation)return;acceptResults=false;idle();say(errorMessage(error))},
        });
        await session.start();if(token!==generation)return;
        timer=setTimeout(stopVoice,10*60*1000);
      }catch(error){if(token===generation){session?.cancel();acceptResults=false;idle();say(errorMessage(error))}}
    }
    mic.onclick=()=>phase==='idle'?startVoice():stopVoice();cancel.onclick=()=>cancelVoice();
    input.addEventListener('input',()=>{
      if(phase!=='idle'&&!settingInput){acceptResults=false;cancelVoice(false);say('Dictation stopped so you can edit your draft.')}
    });
    form.addEventListener('submit',event=>{if(phase!=='idle'){event.preventDefault();event.stopImmediatePropagation();say('Stop voice input before sending.')}},true);
    window.addEventListener('pagehide',()=>{if(phase!=='idle')cancelVoice(false)});
    document.addEventListener('visibilitychange',()=>{if(document.hidden&&phase!=='idle')stopVoice()});
    const settings=document.querySelector('#settings');
    if(settings){
      const section=make('section','voice-settings');
      section.innerHTML='<h2>Voice input</h2><p>On-device speech works in both editions without an API key. English speech files download once (about 45 MB) and stay on this device for offline use. Your microphone audio stays on this device.</p><label for="voiceMode">Voice mode</label><select id="voiceMode"><option value="local">On-device speech · English</option><option value="browser">Browser dictation</option></select><label for="voiceLanguage">Browser dictation language</label><input id="voiceLanguage" placeholder="en-US" maxlength="40"><p class="voice-help">Browser dictation supports your browser’s languages and may use its speech service. Click the microphone to start and again to stop. × discards this dictation. Text appears as you speak; send it when ready.</p>';
      const heading=[...settings.querySelectorAll('h2')].find(node=>node.textContent==='AI connection');
      if(heading)heading.before(section);else settings.append(section);
      const mode=section.querySelector('#voiceMode'),language=section.querySelector('#voiceLanguage');
      mode.value=prefs.mode;language.value=prefs.language;language.disabled=prefs.mode!=='browser';
      const save=()=>{
        if(phase!=='idle')stopVoice();prefs={mode:mode.value,language:language.value.trim()||navigator.language||'en-US'};
        language.disabled=prefs.mode!=='browser';try{localStorage.setItem(preferenceKey,JSON.stringify(prefs))}catch(_){}
      };
      mode.addEventListener('change',save);language.addEventListener('change',save);
    }
    refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
