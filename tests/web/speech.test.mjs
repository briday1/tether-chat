import test from 'node:test';
import assert from 'node:assert/strict';
import {localSpeech,joinTranscript} from '../../tether/speech.mjs';

function fixture({permission=false,worklet=false,latePermission=false}={}){
  const state={text:[],status:[],errors:[],trackStopped:0,closed:0,workersStopped:0};
  class Model {
    constructor(){this.handlers={};state.model=this;queueMicrotask(()=>this.handlers.load?.({result:true}))}
    on(type,fn){this.handlers[type]=fn}
    terminate(){state.workersStopped++}
    get KaldiRecognizer(){return class {
      constructor(){this.handlers={};state.recognizer=this}
      on(type,fn){this.handlers[type]=fn}
      acceptWaveformFloat(data){state.samples=(state.samples||0)+data.length;queueMicrotask(()=>this.handlers.partialresult?.({result:{partial:'live words'}}))}
      retrieveFinalResult(){queueMicrotask(()=>this.handlers.result?.({result:{text:'live words complete'}}))}
      remove(){}
    }}
  }
  class Audio {
    constructor(){this.sampleRate=16000;if(worklet)this.audioWorklet={addModule:async()=>{}}}
    resume(){return Promise.resolve()}
    close(){state.closed++;return Promise.resolve()}
    createMediaStreamSource(){return {connect(){},disconnect(){}}}
    createScriptProcessor(){return state.node={onaudioprocess:null,connect(){},disconnect(){}}}
    createGain(){return {gain:{value:0},connect(){},disconnect(){}}}
  }
  class Worklet {
    constructor(){state.node=this;this.port={onmessage:null,postMessage(){queueMicrotask(()=>{
      state.node.port.onmessage?.({data:new Float32Array(20)});state.node.port.onmessage?.({data:'flushed'});
    })}}}
    connect(){} disconnect(){}
  }
  globalThis.window={Vosk:{Model},AudioContext:Audio,...(worklet?{AudioWorkletNode:Worklet}:{})};
  globalThis.AudioWorkletNode=Worklet;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:async()=>{
    if(latePermission)await new Promise(resolve=>{state.permission=resolve});
    if(permission)throw new DOMException('Denied','NotAllowedError');
    return {getTracks:()=>[{stop(){state.trackStopped++}}]};
  }}}});
  state.session=localSpeech({onText:text=>state.text.push(text),onStatus:text=>state.status.push(text),onError:error=>state.errors.push(error)});
  return state;
}

test('live partial text precedes Stop and finalization preserves the last worklet samples',async()=>{
  const f=fixture({worklet:true});await f.session.start();
  f.node.port.onmessage({data:new Float32Array(100)});await Promise.resolve();
  assert.equal(f.text.at(-1),'live words');assert.equal(f.trackStopped,0);
  await f.session.stop();assert.equal(f.text.at(-1),'live words complete');
  assert.equal(f.samples,120);assert.equal(f.trackStopped,1);assert.equal(f.workersStopped,1);
  assert.equal(f.closed,1);assert.equal(f.errors.length,0);
});

test('cancel ignores late recognition and frees microphone, worker and audio context',async()=>{
  const f=fixture();await f.session.start();
  f.node.onaudioprocess({inputBuffer:{getChannelData:()=>new Float32Array(4096)}});
  f.session.cancel();await Promise.resolve();
  assert.equal(f.text.length,0);assert.equal(f.trackStopped,1);assert.equal(f.workersStopped,1);assert.equal(f.closed,1);
  f.session.cancel();assert.equal(f.trackStopped,1);
});

test('cancelling a pending permission request stops a stream acquired later',async()=>{
  const f=fixture({latePermission:true}),started=f.session.start();await Promise.resolve();
  f.session.cancel();f.permission();await started;
  assert.equal(f.trackStopped,1);assert.equal(f.closed,1);assert.equal(f.model,undefined);
});

test('permission denial closes the audio context without loading speech or changing the draft',async()=>{
  const f=fixture({permission:true});await assert.rejects(f.session.start(),{name:'NotAllowedError'});
  assert.equal(f.closed,1);assert.equal(f.model,undefined);assert.equal(f.text.length,0);
});

test('spoken text respects existing draft whitespace',()=>{
  assert.equal(joinTranscript('Typed first.','more words'),'Typed first. more words');
  assert.equal(joinTranscript('Typed first.\n','more words'),'Typed first.\nmore words');
  assert.equal(joinTranscript('Typed first.',''),'Typed first.');
});
