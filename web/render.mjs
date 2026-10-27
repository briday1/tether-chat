/* Escape every text/attribute. Only explicit Markdown constructs create HTML. */
export const escapeHTML = text => String(text).replace(/[&<>"']/g,c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function cells(line) {
  const parts=[];let part='',lastPipe=false;
  for(let i=0,s=line.trim();i<s.length;i++) {
    const c=s[i];lastPipe=false;
    if(c==='\\' && i+1<s.length){part+=c+s[++i];continue}
    if(c==='|'){parts.push(part.trim());part='';lastPipe=true}else part+=c;
  }
  parts.push(part.trim());
  if(line.trim().startsWith('|'))parts.shift();
  if(lastPipe)parts.pop();
  return parts;
}

export function renderMarkdown(text, config={base:'/'}) {
  function inline(value,depth=0,links=true) {
    if(depth>8)return escapeHTML(value);
    let html='';
    for(let i=0;i<value.length;) {
      const rest=value.slice(i);let match;
      if((match=rest.match(/^\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/))) {
        html+=escapeHTML(match[1]);i+=match[0].length;continue;
      }
      if((match=rest.match(/^`([^`\n]+)`/))) {
        html+='<code>'+escapeHTML(match[1])+'</code>';i+=match[0].length;continue;
      }
      if(links && (match=rest.match(/^\[((?:\\.|[^\]\\\n])+)\]\(([^\s)]+)\)/))) {
        let target=match[2];
        if(/^\/board(?=[#?]|$)/.test(target))target=config.base+'board.html'+target.slice(6);
        else if(/^\/snapshots(?=[#?]|$)/.test(target))target=config.base+'snapshots.html'+target.slice(10);
        html+=/^(?:https?:\/\/|mailto:|\/[^/])/.test(target)
          ? `<a href="${escapeHTML(target)}" rel="noopener noreferrer">${inline(match[1],depth+1,false)}</a>`
          : escapeHTML(match[0]);
        i+=match[0].length;continue;
      }
      if((match=rest.match(/^(\*\*|__)(?=\S)([^\n]+?\S|\S)\1/))) {
        html+='<strong>'+inline(match[2],depth+1,links)+'</strong>';i+=match[0].length;continue;
      }
      if((match=rest.match(/^\*(?=\S)([^*\n]*\S)\*/))) {
        html+='<em>'+inline(match[1],depth+1,links)+'</em>';i+=match[0].length;continue;
      }
      html+=escapeHTML(value[i++]);
    }
    return html;
  }
  const lines=String(text||'').split(/\r?\n/),blocks=[];
  let paragraph=[],list=[],code=null;
  function listHTML(items) {
    let index=0;
    const group=indent=>{
      const type=items[index].type;let html='<'+type+'>';
      while(index<items.length && items[index].indent===indent && items[index].type===type) {
        html+='<li>'+inline(items[index++].text);
        while(index<items.length && items[index].indent>indent)html+=group(items[index].indent);
        html+='</li>';
      }
      return html+'</'+type+'>';
    };
    let html='';while(index<items.length)html+=group(items[index].indent);return html;
  }
  const flush=()=>{
    if(paragraph.length){blocks.push('<p>'+paragraph.map(s=>inline(s)).join('<br>')+'</p>');paragraph=[]}
    if(list.length){blocks.push(listHTML(list));list=[]}
  };
  for(let index=0;index<lines.length;index++) {
    const line=lines[index];
    if(line.startsWith('```')){flush();if(code!==null){blocks.push('<pre><code>'+escapeHTML(code.join('\n'))+'</code></pre>');code=null}else code=[];continue}
    if(code!==null){code.push(line);continue}
    const header=cells(line),divider=index+1<lines.length?cells(lines[index+1]):[];
    if(line.includes('|') && header.length===divider.length && divider.length>1 && divider.every(s=>/^:?-{3,}:?$/.test(s))) {
      flush();const rows=[];index++;
      while(index+1<lines.length && lines[index+1].trim() && lines[index+1].includes('|')) {
        const row=cells(lines[index+1]);if(row.length>header.length)break;
        while(row.length<header.length)row.push('');
        rows.push('<tr>'+row.map(cell=>'<td>'+inline(cell)+'</td>').join('')+'</tr>');index++;
      }
      blocks.push('<table><thead><tr>'+header.map(cell=>'<th>'+inline(cell)+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table>');continue;
    }
    const heading=line.match(/^(#{1,4})\s+(.+)/),item=line.match(/^(\s*)([-*]|\d+\.)\s+(.+)/);
    if(heading){flush();blocks.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`)}
    else if(item){if(paragraph.length)flush();list.push({indent:item[1].replace(/\t/g,'    ').length,type:/\d/.test(item[2])?'ol':'ul',text:item[3]})}
    else if(!line.trim())flush();
    else {if(list.length)flush();paragraph.push(line)}
  }
  flush();if(code!==null)blocks.push('<pre><code>'+escapeHTML(code.join('\n'))+'</code></pre>');
  return blocks.join('');
}
