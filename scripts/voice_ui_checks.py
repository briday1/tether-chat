"""Synthetic microphone fixtures shared by desktop and standalone-browser CI."""
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
  const track={stop(){window.voiceTrackStopped=true}};
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{window.voiceTrackStopped=false;return {getTracks:()=>[track]}}}});
  class Recorder {
    static isTypeSupported(type){return type==='audio/webm;codecs=opus'}
    constructor(){this.state='inactive';this.mimeType='audio/webm;codecs=opus'}
    start(){this.state='recording'}
    stop(){if(this.state==='inactive')return;this.state='inactive';queueMicrotask(()=>{this.ondataavailable?.({data:new Blob(['synthetic audio'],{type:this.mimeType})});this.onstop?.()})}
  }
  window.MediaRecorder=Recorder;
})();"""


def check_dictation(page,frame):
    from playwright.sync_api import expect
    field=frame.get_by_label('Message tether')
    field.fill('Typed first.')
    before=frame.locator('.bubble.user').count()
    frame.get_by_role('button',name='Start voice input',exact=True).click()
    expect(field).to_have_value('Typed first. Spoken words for review.')
    expect(frame.get_by_role('button',name='Send',exact=True)).to_be_disabled()
    frame.get_by_role('button',name='Stop voice input',exact=True).click()
    expect(frame.get_by_role('button',name='Start voice input',exact=True)).to_be_enabled()
    expect(field).to_have_value('Typed first. Spoken words for review.')
    assert frame.locator('.bubble.user').count()==before,'Dictation sent a chat automatically'
    field.fill('Keep this draft.')
    field.evaluate('(element)=>element.ownerDocument.defaultView.voicePermissionDenied=true')
    frame.get_by_role('button',name='Start voice input',exact=True).click()
    expect(frame.locator('#voiceStatus')).to_contain_text('denied')
    expect(field).to_have_value('Keep this draft.')
    field.evaluate('(element)=>element.ownerDocument.defaultView.voicePermissionDenied=false')
    field.fill('')


def check_recording(page,frame):
    from playwright.sync_api import expect
    frame.get_by_role('button',name='Settings',exact=True).click()
    frame.get_by_label('Voice mode',exact=True).select_option('provider')
    frame.get_by_label('Provider transcription model',exact=True).fill('test-transcriber')
    frame.get_by_label('Provider transcription model',exact=True).press('Tab')
    frame.get_by_role('button',name='Close settings').click()
    field=frame.get_by_label('Message tether');field.fill('Before recording.')
    before=frame.locator('.bubble.user').count()
    frame.get_by_role('button',name='Start voice input',exact=True).click()
    expect(frame.get_by_role('button',name='Stop voice input',exact=True)).to_be_visible()
    frame.get_by_role('button',name='Stop voice input',exact=True).click()
    expect(frame.locator('#voiceStatus')).to_contain_text('Transcript added')
    expect(field).to_have_value('Before recording. Recorded voice draft.')
    assert frame.locator('.bubble.user').count()==before,'Recorded audio sent a chat automatically'
    assert field.evaluate('(element)=>element.ownerDocument.defaultView.voiceTrackStopped')
    field.fill('Cancel keeps this draft.')
    frame.get_by_role('button',name='Start voice input',exact=True).click()
    expect(frame.get_by_role('button',name='Stop voice input',exact=True)).to_be_visible()
    frame.get_by_role('button',name='Cancel voice input',exact=True).click()
    expect(frame.locator('#voiceStatus')).to_contain_text('cancelled')
    expect(field).to_have_value('Cancel keeps this draft.')
    assert field.evaluate('(element)=>element.ownerDocument.defaultView.voiceTrackStopped')
    frame.get_by_role('button',name='Settings',exact=True).click()
    frame.get_by_label('Voice mode',exact=True).select_option('auto')
    frame.get_by_role('button',name='Close settings').click();field.fill('')
