/* Vosk runs in a worker on this device. Only public speech files are downloaded. */
export const LIBRARY='https://cdn.jsdelivr.net/npm/vosk-browser@0.0.8/dist/vosk.js';
export const INTEGRITY='sha384-nqyY8clHf93uBYFkgkACShMTuvE3U57yXSJaf0Ws+XgzcoUe6OB/1BiOfHqKOWeg';
export const MODEL='https://ccoreilly.github.io/vosk-browser/models/vosk-model-small-en-us-0.15.tar.gz';
const CACHE='tether-speech:vosk-0.0.8';
let libraryPromise;

async function library(){
  if(window.Vosk)return window.Vosk;
  if(!libraryPromise)libraryPromise=(async()=>{
    // Keep the small runtime available offline independently of the app's release cache.
    const cache=await caches.open(CACHE).catch(()=>null);
    let response=await cache?.match(LIBRARY);
    if(!response){
      response=await fetch(LIBRARY,{mode:'cors',credentials:'omit',integrity:INTEGRITY});
      if(!response.ok)throw Error('Could not download the speech engine. Check your internet connection and try again.');
      await cache?.put(LIBRARY,response.clone()).catch(()=>{});
    }
    const bytes=await response.arrayBuffer();
    const hash=await crypto.subtle.digest('SHA-384',bytes);
    if('sha384-'+btoa(String.fromCharCode(...new Uint8Array(hash)))!==INTEGRITY){
      await cache?.delete(LIBRARY);throw Error('The speech engine download was incomplete. Try again.');
    }
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/javascript'}));
    try{
      await new Promise((resolve,reject)=>{
        const script=document.createElement('script');script.src=url;
        script.onload=()=>{script.remove();resolve()};script.onerror=()=>{script.remove();reject(Error('Could not open the on-device speech engine.'))};
        document.head.append(script);
      });
    }finally{URL.revokeObjectURL(url)}
    return window.Vosk;
  })().catch(error=>{libraryPromise=null;throw error});
  return libraryPromise;
}

export function joinTranscript(before,spoken){
  return before+(before&&spoken&&!/\s$/.test(before)?' ':'')+spoken;
}

// A session owns its worker, audio graph and microphone. Stop/cancel always frees them.
export function localSpeech({onText,onStatus,onError}){
  let model,recognizer,context,stream,source,node,gain,stopped=false,finishing=false,finalRequested=false,finishResult,finishTimer,flushResult,drainResult,pending=0;
  let committed='',partial='';
  const publish=()=>onText(joinTranscript(committed,partial).trim());
  const releaseAudio=()=>{
    source?.disconnect();node?.disconnect();gain?.disconnect();if(node?.port)node.port.onmessage=null;
    if(node&&'onaudioprocess' in node)node.onaudioprocess=null;
    for(const track of stream?.getTracks()||[])track.stop();stream=null;
    context?.close().catch(()=>{});context=null;
  };
  const dispose=()=>{clearTimeout(finishTimer);recognizer?.remove();recognizer=null;model?.terminate();model=null;flushResult?.();drainResult?.()};
  const fail=error=>{if(stopped)return;stopped=true;releaseAudio();dispose();finishResult?.();onError(error)};
  const processed=()=>{pending=Math.max(0,pending-1);if(!pending)drainResult?.()};
  const audio=data=>{if(!stopped&&recognizer){pending++;recognizer.acceptWaveformFloat(data,context.sampleRate)}};
  async function start(){
    if(!navigator.mediaDevices?.getUserMedia)throw Error('Microphone access needs HTTPS or localhost and a supported browser.');
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio)throw Error('On-device speech is unavailable in this browser. Choose Browser dictation in Settings.');
    // Resume from the click's user gesture, including on iPhone.
    context=new Audio();
    try{
      await context.resume();if(stopped)return;
      onStatus('Preparing on-device speech… First use downloads about 45 MB. Wait for Listening before speaking.');
      const acquired=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(stopped){for(const track of acquired.getTracks())track.stop();return}
      stream=acquired;
      const Vosk=await library();if(stopped)return;
      model=new Vosk.Model(MODEL,-1);
      await new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>reject(Error('Speech setup took too long. Check internet access to the speech files and try again.')),120000);
        const done=fn=>value=>{clearTimeout(timeout);fn(value)};
        model.on('load',done(message=>message.result?resolve():reject(Error('Could not prepare on-device speech. Try again.'))));
        model.on('error',done(message=>reject(Error(message.error||'Could not load the speech files.'))));
        finishResult=done(resolve);
      });
      finishResult=null;if(stopped)return;
      recognizer=new model.KaldiRecognizer(context.sampleRate);
      recognizer.on('partialresult',message=>{if(stopped)return;partial=message.result.partial||'';publish();processed()});
      recognizer.on('result',message=>{
        if(stopped)return;committed=joinTranscript(committed,(message.result.text||'').trim());partial='';publish();
        if(finalRequested){stopped=true;dispose();finishResult?.()}else processed();
      });
      recognizer.on('error',message=>fail(Error(message.error||'On-device speech stopped. Try again.')));
      source=context.createMediaStreamSource(stream);
      // AudioWorklet avoids processing microphone buffers on the UI thread.
      if(context.audioWorklet && window.AudioWorkletNode){
        const worklet=URL.createObjectURL(new Blob([`class Capture extends AudioWorkletProcessor {
          constructor(){super();this.buffer=new Float32Array(4096);this.offset=0;this.port.onmessage=()=>{
            if(this.offset)this.port.postMessage(this.buffer.slice(0,this.offset));this.offset=0;this.port.postMessage('flushed')}}
          process(inputs){const data=inputs[0]?.[0];if(data)for(const value of data){this.buffer[this.offset++]=value;
            if(this.offset===this.buffer.length){this.port.postMessage(this.buffer,[this.buffer.buffer]);this.buffer=new Float32Array(4096);this.offset=0}}
            return true}
        } registerProcessor('tether-speech-capture',Capture);`],{type:'application/javascript'}));
        try{await context.audioWorklet.addModule(worklet)}finally{URL.revokeObjectURL(worklet)}
        if(stopped)return;
        node=new AudioWorkletNode(context,'tether-speech-capture');
        node.port.onmessage=event=>event.data==='flushed'?flushResult?.():audio(event.data);
      }else{
        node=context.createScriptProcessor(4096,1,1);
        node.onaudioprocess=event=>{if(!finishing)audio(event.inputBuffer.getChannelData(0))};
      }
      gain=context.createGain();gain.gain.value=0;
      source.connect(node);node.connect(gain);gain.connect(context.destination);
      onStatus('Listening… Click the microphone again to stop.');
    }catch(error){if(!stopped){stopped=true;releaseAudio();dispose();throw error}}
  }
  return {
    start,
    async stop(){
      if(stopped)return;if(!recognizer){this.cancel();return}
      finishing=true;source?.disconnect();
      await new Promise(resolve=>{
        finishResult=resolve;
        finishTimer=setTimeout(()=>{stopped=true;releaseAudio();dispose();resolve()},3000);
        (async()=>{
          if(node?.port)await new Promise(done=>{flushResult=done;node.port.postMessage('flush')});
          if(stopped)return;releaseAudio();
          if(pending)await new Promise(done=>{drainResult=done});
          if(stopped)return;finalRequested=true;recognizer.retrieveFinalResult();
        })().catch(fail);
      });
    },
    cancel(){if(stopped)return;stopped=true;releaseAudio();dispose();finishResult?.()},
  };
}
