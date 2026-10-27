/* Shared microphone input: editable dictation, never an automatic chat submission. */
(() => {
  function init(){
    const input=document.querySelector('#message'),form=document.querySelector('#composer');if(!input||!form)return;
    const namespace=window.TETHER_CONFIG?'tether-web:'+window.TETHER_CONFIG.base:'tether-desktop:'+location.port;
    const preferenceKey=namespace+':voice';let prefs={mode:'auto',language:navigator.language||'en-US',model:'whisper-1'};
    try{prefs={...prefs,...JSON.parse(localStorage.getItem(preferenceKey)||'{}')}}catch(_){}
    const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n};
    const mic=make('button','voice-button'),cancel=make('button','voice-button voice-cancel'),status=make('div','voice-status');
    mic.type=cancel.type='button';mic.id='voiceInput';cancel.id='voiceCancel';cancel.hidden=true;status.id='voiceStatus';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    mic.innerHTML='<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>';
    cancel.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
    cancel.title='Cancel voice input';cancel.setAttribute('aria-label','Cancel voice input');
    const send=document.querySelector('#send');send.before(mic,cancel);form.append(status);
    let phase='idle',recognizer=null,recorder=null,stream=null,chunks=[],timer=null,controller=null,generation=0,original='',acceptResults=true,settingInput=false,useRecorderNext=false;
    const settingsURL='/api/settings',transcribeURL='/api/voice/transcribe';
    function refresh(){
      const active=phase!=='idle';mic.classList.toggle('listening',phase==='listening'||phase==='recording');
      mic.disabled=phase==='transcribing'||phase==='starting';mic.setAttribute('aria-pressed',String(phase==='listening'||phase==='recording'));
      mic.title=phase==='listening'||phase==='recording'?'Stop voice input':phase==='transcribing'?'Transcribing voice input':'Start voice input';
      mic.setAttribute('aria-label',phase==='listening'||phase==='recording'?'Stop voice input':phase==='transcribing'?'Transcribing voice input':'Start voice input');
      cancel.hidden=!active;send.disabled=active;
    }
    function say(text){status.textContent=text}
    function writeDraft(text){settingInput=true;input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));settingInput=false}
    function append(text){const before=input.value;writeDraft(before+(before&&!/\s$/.test(before)?' ':'')+text.trim());input.focus()}
    function release(){clearTimeout(timer);timer=null;for(const track of stream?.getTracks()||[])track.stop();stream=null}
    function idle(){phase='idle';release();refresh()}
    function cancelVoice(){
      const restoreSpeech=!!recognizer&&acceptResults;
      generation++;acceptResults=false;controller?.abort();controller=null;
      if(recognizer){try{recognizer.abort()}catch(_){}recognizer=null}
      if(recorder && recorder.state!=='inactive'){recorder.onstop=null;try{recorder.stop()}catch(_){}}
      recorder=null;chunks=[];if(restoreSpeech)writeDraft(original);idle();say('Voice input cancelled.');
    }
    function speech(){
      const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition;
      if(!Constructor)return false;
      const token=++generation;original=input.value;acceptResults=true;phase='starting';refresh();say('Opening microphone…');
      try{
        recognizer=new Constructor();recognizer.lang=prefs.language;recognizer.continuous=true;recognizer.interimResults=true;
        recognizer.onstart=()=>{if(token!==generation)return;phase='listening';refresh();say('Listening… Stop when finished, then review your message. Browser dictation may use its speech service.')};
        recognizer.onresult=event=>{
          if(token!==generation||!acceptResults)return;
          const text=Array.from(event.results).map(result=>result[0]?.transcript||'').join(' ').trim();
          writeDraft(original+(original&&!/\s$/.test(original)?' ':'')+text);
        };
        recognizer.onerror=event=>{
          if(token!==generation)return;acceptResults=false;
          if(['not-allowed','service-not-allowed'].includes(event.error))say('Microphone or speech access was denied. Allow it in your browser or system settings.');
          else if(event.error==='no-speech')say('No speech was detected. Your draft is unchanged.');
          else if(event.error==='audio-capture')say('No microphone is available. Check your microphone connection and permissions.');
          else{useRecorderNext=true;say('Browser dictation is unavailable. Tap the microphone again to record for your configured AI provider, or choose a voice mode in Settings.');}
        };
        recognizer.onend=()=>{if(token!==generation)return;const hadError=!acceptResults;recognizer=null;idle();if(!hadError)say('Dictation stopped. Review your message before sending.')};
        recognizer.start();return true;
      }catch(_){recognizer=null;idle();useRecorderNext=true;say('Browser dictation could not start. Tap the microphone again to use provider transcription.');return true}
    }
    async function record(){
      const token=++generation;phase='starting';refresh();say('Preparing microphone…');
      try{
        if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Audio recording is unavailable here. Try a current browser or your keyboard’s microphone.');
        const response=await fetch(settingsURL),connection=await response.json();
        if(!response.ok||!connection.has_key)throw Error('Configure or unlock your AI connection in Settings before using provider transcription.');
        if(token!==generation)return;
        say('Opening microphone. This recording will be sent to your configured AI provider when you stop.');
        const acquired=await navigator.mediaDevices.getUserMedia({audio:true});
        if(token!==generation){for(const track of acquired.getTracks())track.stop();return}
        stream=acquired;const type=['audio/webm;codecs=opus','audio/mp4','audio/webm','audio/ogg;codecs=opus'].find(value=>MediaRecorder.isTypeSupported(value));
        recorder=type?new MediaRecorder(stream,{mimeType:type}):new MediaRecorder(stream);chunks=[];let size=0;
        recorder.ondataavailable=event=>{if(event.data.size){chunks.push(event.data);size+=event.data.size;if(size>20*1024*1024){cancelVoice();say('The recording reached the size limit. Try a shorter recording.')}}};
        recorder.onerror=()=>{cancelVoice();say('The microphone recording failed. Your draft is unchanged.')};
        recorder.onstop=async()=>{
          if(token!==generation)return;
          const mime=recorder.mimeType||chunks[0]?.type||'audio/webm',blob=new Blob(chunks,{type:mime});recorder=null;chunks=[];release();
          if(!blob.size){idle();say('No audio was recorded.');return}
          phase='transcribing';refresh();say('Transcribing with your configured AI provider…');controller=new AbortController();
          try{
            const payload=new FormData(),extension=mime.includes('mp4')?'m4a':mime.includes('ogg')?'ogg':'webm';
            payload.append('file',blob,'voice.'+extension);payload.append('model',prefs.model);payload.append('provider_base',connection.base_url);
            const result=await fetch(transcribeURL,{method:'POST',body:payload,signal:controller.signal});
            const body=await result.json();if(!result.ok)throw Error(typeof body.detail==='string'?body.detail:'Transcription failed.');
            if(token!==generation)return;if(typeof body.text!=='string'||!body.text.trim())throw Error('No speech was recognized.');
            append(body.text);say('Transcript added. Review your message before sending.');
          }catch(error){if(token===generation)say(error.name==='AbortError'?'Transcription cancelled.':error.message)}
          finally{if(token===generation){controller=null;idle()}}
        };
        recorder.start(1000);phase='recording';refresh();say('Recording… Stop to transcribe with your AI provider, or cancel to discard.');
        timer=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop()},5*60*1000);
      }catch(error){if(token===generation){idle();say(error.name==='NotAllowedError'?'Microphone access was denied. Allow it in browser or system settings.':error.message)}}
    }
    mic.onclick=()=>{
      if(phase==='listening'){phase='starting';refresh();try{recognizer?.stop()}catch(_){idle()}return}
      if(phase==='recording'){phase='transcribing';refresh();if(recorder?.state==='recording')recorder.stop();return}if(phase!=='idle')return;
      if(prefs.mode!=='provider'&&!useRecorderNext&&speech())return;
      if(prefs.mode==='browser'){say('Browser dictation is unavailable. Choose Provider transcription in Voice input settings.');return}
      useRecorderNext=false;record();
    };
    cancel.onclick=cancelVoice;
    input.addEventListener('input',()=>{if(phase==='listening'&&!settingInput){acceptResults=false;recognizer?.stop();say('Dictation stopped so you can edit your draft.')}});
    form.addEventListener('submit',event=>{if(phase!=='idle'){event.preventDefault();event.stopImmediatePropagation();say('Stop voice input and review your message before sending.')}},true);
    window.addEventListener('pagehide',()=>{if(phase!=='idle')cancelVoice()});
    const settings=document.querySelector('#settings');
    if(settings){
      const section=make('section','voice-settings');section.innerHTML='<h2>Voice input</h2><p>Browser dictation may use your browser’s speech service. Provider transcription sends the recording to your configured AI provider using your key.</p><label for="voiceMode">Voice mode</label><select id="voiceMode"><option value="auto">Automatic</option><option value="browser">Browser dictation</option><option value="provider">Provider transcription</option></select><label for="voiceLanguage">Dictation language</label><input id="voiceLanguage" placeholder="en-US" maxlength="40"><label for="voiceModel">Provider transcription model</label><input id="voiceModel" placeholder="whisper-1" maxlength="200"><p class="voice-help">The provider must support audio/transcriptions. Choose its transcription model here; this is separate from your chat model. Voice input fills a draft for review and never sends a chat automatically.</p>';
      const heading=[...settings.querySelectorAll('h2')].find(node=>node.textContent==='AI connection');
      if(heading)heading.before(section);else settings.append(section);
      const mode=section.querySelector('#voiceMode'),language=section.querySelector('#voiceLanguage'),model=section.querySelector('#voiceModel');
      mode.value=['auto','browser','provider'].includes(prefs.mode)?prefs.mode:'auto';language.value=prefs.language;model.value=prefs.model;
      const save=()=>{prefs={mode:mode.value,language:language.value.trim()||navigator.language||'en-US',model:model.value.trim()||'whisper-1'};
        try{localStorage.setItem(preferenceKey,JSON.stringify(prefs))}catch(_){}useRecorderNext=false};
      for(const node of [mode,language,model])node.addEventListener('change',save);
    }
    refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
