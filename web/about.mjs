// Browser-only About: the brand is the quiet entry point, not a persistent footer.
const brand=document.querySelector('.brand');
if(brand){
  const trigger=document.createElement('button');trigger.type='button';trigger.className=brand.className+' about-trigger';
  trigger.setAttribute('aria-label','About tether');trigger.setAttribute('aria-haspopup','dialog');
  trigger.append(...brand.childNodes);brand.replaceWith(trigger);
  const dialog=document.createElement('dialog');dialog.className='tether-about';dialog.setAttribute('aria-labelledby','tether-about-title');
  const title=document.createElement('h2');title.id='tether-about-title';title.textContent='About tether';
  const product=document.createElement('p');product.textContent='tether-home · Your household assistant';
  const version=document.createElement('p');version.className='muted';version.textContent='Version '+(window.TETHER_CONFIG?.version||'unknown');
  const links=document.createElement('nav');links.setAttribute('aria-label','Legal information');
  for(const [name,path] of [['Privacy policy','privacy.html'],['Terms of service','terms.html']]){
    const link=document.createElement('a');link.textContent=name;link.href=new URL((window.TETHER_CONFIG?.base||'./')+path,location.origin).href;link.target='_blank';link.rel='noopener noreferrer';links.append(link);
  }
  const close=document.createElement('button');close.type='button';close.className='secondary';close.textContent='Close';close.autofocus=true;
  dialog.append(title,product,version,links,close);document.body.append(dialog);
  trigger.addEventListener('click',()=>{if(!dialog.open)dialog.showModal()});
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>trigger.focus());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close()}});
}
