/* Escape first; only a small, explicit Markdown subset can create HTML. */
export const escapeHTML = text => String(text).replace(/[&<>"']/g,c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderMarkdown(text, config) {
  const inline = value => {
    let safe=escapeHTML(value);
    safe=safe.replace(/\[([^\]\n]+)\]\(([^\s)]+)\)/g,(whole,label,target) => {
      target=target.replace(/&amp;/g,'&');
      if (target.startsWith('/board')) target=config.base+'board.html'+target.slice(6);
      else if (target.startsWith('/snapshots')) target=config.base+'snapshots.html'+target.slice(10);
      if (!/^(?:https?:\/\/|\/[^/])/.test(target)) return whole;
      return `<a href="${escapeHTML(target)}" rel="noopener noreferrer">${label}</a>`;
    });
    return safe.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
  };
  const lines=String(text).split('\n'), blocks=[]; let paragraph=[], list=[], code=null;
  const flush=()=>{if(paragraph.length){blocks.push('<p>'+paragraph.map(inline).join('<br>')+'</p>');paragraph=[]}if(list.length){blocks.push('<ul>'+list.map(s=>'<li>'+inline(s)+'</li>').join('')+'</ul>');list=[]}};
  for(const line of lines){
    if(line.startsWith('```')){flush();if(code!==null){blocks.push('<pre><code>'+escapeHTML(code.join('\n'))+'</code></pre>');code=null}else code=[];continue}
    if(code!==null){code.push(line);continue}
    const heading=line.match(/^(#{1,3})\s+(.+)/),item=line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)/);
    if(heading){flush();blocks.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`)}
    else if(item){if(paragraph.length)flush();list.push(item[1])}
    else if(!line.trim())flush();else{if(list.length)flush();paragraph.push(line)}
  }
  flush();if(code!==null)blocks.push('<pre><code>'+escapeHTML(code.join('\n'))+'</code></pre>');return blocks.join('');
}
