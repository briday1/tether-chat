"""Deterministic live speech events shared by desktop and standalone-browser CI."""
MOCKS="""(() => {
  class Recognition {
    start(){this.active=true;setTimeout(()=>{if(!this.active)return;
      if(window.voicePermissionDenied){this.onerror?.({error:'not-allowed'});this.onend?.();return}
      this.onstart?.();setTimeout(()=>{if(this.active){const event={results:[[{transcript:'Spoken words for review.'}]]};this.onresult?.(event);this.onresult?.(event)}},100);
    },0)}
    stop(){this.active=false;queueMicrotask(()=>this.onend?.())}
    abort(){this.active=false;queueMicrotask(()=>this.onend?.())}
  }
  window.SpeechRecognition=Recognition;window.webkitSpeechRecognition=Recognition;
  class Model {
    constructor(){this.handlers={};window.voiceModel=this;setTimeout(()=>this.handlers.load?.({result:true}),20)}
    on(event,handler){this.handlers[event]=handler}
    terminate(){window.voiceWorkerStopped=true}
    get KaldiRecognizer(){return class {
      constructor(){this.handlers={};window.voiceRecognizer=this}
      on(event,handler){this.handlers[event]=handler}
      acceptWaveformFloat(){this.handlers.partialresult?.({result:{partial:'Live words in progress'}})}
      retrieveFinalResult(){setTimeout(()=>this.handlers.result?.({result:{text:'Live words in progress finalized.'}}),20)}
      remove(){}
    }}
  }
  window.Vosk={Model};
  const track={stop(){window.voiceTrackStopped=true}};
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{
    if(window.voicePermissionDenied)throw new DOMException('Denied','NotAllowedError');
    window.voiceTrackStopped=false;window.voiceWorkerStopped=false;return {getTracks:()=>[track]};
  }}});
  class Audio {
    constructor(){this.sampleRate=48000;window.voiceContext=this}
    resume(){return Promise.resolve()}
    close(){window.voiceContextClosed=true;return Promise.resolve()}
    createMediaStreamSource(){return {connect(node){setTimeout(()=>node.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(4096)}}),100)},disconnect(){}}}
    createScriptProcessor(){return {connect(){},disconnect(){},onaudioprocess:null}}
    createGain(){return {gain:{value:0},connect(){},disconnect(){}}}
  }
  window.AudioContext=Audio;
})();"""


def mode(frame,value):
    frame.get_by_role('button',name='Settings',exact=True).click()
    frame.get_by_label('Voice mode',exact=True).select_option(value)
    frame.get_by_role('button',name='Close settings').click()


def check_dictation(page,frame):
    from playwright.sync_api import expect
    mode(frame,'browser')
    field=frame.get_by_label('Message tether');field.fill('Typed first.')
    before=frame.locator('.bubble.user').count()
    frame.locator('#voiceInput').click()
    expect(field).to_have_value('Typed first. Spoken words for review.')
    expect(frame.get_by_role('button',name='Send',exact=True)).to_be_disabled()
    frame.locator('#voiceInput').click()
    expect(frame.locator('#voiceInput')).to_have_attribute('aria-pressed','false')
    expect(field).to_have_value('Typed first. Spoken words for review.')
    assert frame.locator('.bubble.user').count()==before,'Dictation sent a chat automatically'
    field.fill('Keep this draft.')
    field.evaluate('(element)=>element.ownerDocument.defaultView.voicePermissionDenied=true')
    frame.locator('#voiceInput').click()
    expect(frame.locator('#voiceStatus')).to_contain_text('denied')
    expect(field).to_have_value('Keep this draft.')
    field.evaluate('(element)=>element.ownerDocument.defaultView.voicePermissionDenied=false')
    mode(frame,'local');field.fill('')


def check_recording(page,frame):
    from playwright.sync_api import expect
    mode(frame,'local')
    field=frame.get_by_label('Message tether');field.fill('Before recording.')
    before=frame.locator('.bubble.user').count()
    frame.locator('#voiceInput').click()
    expect(frame.locator('#voiceInput')).to_have_class('voice-button listening')
    # This assertion runs before Stop: text must arrive during capture.
    expect(field).to_have_value('Before recording. Live words in progress')
    for selector in ['#voiceInput','#voiceCancel']:
        styles=frame.locator(selector).evaluate('(e)=>({border:getComputedStyle(e).borderTopWidth,background:getComputedStyle(e).backgroundColor,shadow:getComputedStyle(e).boxShadow})')
        assert styles=={'border':'0px','background':'rgba(0, 0, 0, 0)','shadow':'none'},styles
    assert frame.locator('#voiceInput').evaluate('(e)=>getComputedStyle(e).color!==getComputedStyle(e.ownerDocument.querySelector("#voiceCancel")).color')
    frame.locator('#voiceInput').click()
    expect(frame.locator('#voiceStatus')).to_contain_text('Dictation stopped')
    expect(field).to_have_value('Before recording. Live words in progress finalized.')
    assert frame.locator('.bubble.user').count()==before,'Local speech sent a chat automatically'
    assert field.evaluate('(e)=>e.ownerDocument.defaultView.voiceTrackStopped&&e.ownerDocument.defaultView.voiceWorkerStopped')
    field.fill('Cancel keeps this draft.')
    frame.locator('#voiceInput').click()
    expect(field).to_have_value('Cancel keeps this draft. Live words in progress')
    frame.locator('#voiceCancel').click()
    expect(field).to_have_value('Cancel keeps this draft.')
    expect(frame.locator('#voiceInput')).to_have_attribute('aria-pressed','false')
    assert field.evaluate('(e)=>e.ownerDocument.defaultView.voiceTrackStopped&&e.ownerDocument.defaultView.voiceWorkerStopped')
    frame.locator('#voiceInput').click()
    expect(field).to_have_value('Cancel keeps this draft. Live words in progress')
    field.fill('Manually edited while listening.')
    expect(frame.locator('#voiceInput')).to_have_attribute('aria-pressed','false')
    expect(field).to_have_value('Manually edited while listening.')
    field.evaluate('(e)=>e.ownerDocument.defaultView.voicePermissionDenied=true')
    frame.locator('#voiceInput').click()
    expect(frame.locator('#voiceStatus')).to_contain_text('denied')
    expect(field).to_have_value('Manually edited while listening.')
    field.evaluate('(e)=>e.ownerDocument.defaultView.voicePermissionDenied=false')
    field.fill('')
