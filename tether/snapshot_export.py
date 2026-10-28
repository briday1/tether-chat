"""Deterministic, content-sized PNG and SVG calendars, without browser dependencies."""
from datetime import date, timedelta
from html import escape
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from .snapshots import snapshot

THEMES={
    'light':('#fafaf9','#333b44','#e2e3e3'),
    'dark':('#303438','#f0f2f4','#1f2225'),
    'sage':('#fafcf6','#293d31','#e4e9e0'),
    'rose':('#fff9fc','#463044','#ebe1e6'),
    'sepia':('#fff8e9','#45372a','#e4ded3'),
    'dusk':('#393b54','#f2efff','#24253a'),
    'ocean':('#2d4e58','#f1faf9','#19333b'),
    'solarized-light':('#fdf6e3','#4c4538','#e9e3d1'),
    'solarized-dark':('#164955','#edf7f8','#073541'),
}
COLORS=['#3279c7','#bd4a69','#478d57','#b87527','#8058bc','#168d99',
        '#c0523e','#6b7d27','#a33d9d','#5079a4','#aa7746','#318575',
        '#865b49','#98547e','#567bb9','#a65b28','#658742','#8560aa',
        '#b64e52','#3f8ba9','#8c7332','#4e9180','#b06b86','#636bb4']

def category_color(name):
    value=0
    for char in name.lower():
        # Match JavaScript charCodeAt(0), including non-BMP category names.
        code=int.from_bytes(char.encode('utf-16-le')[:2],'little')
        value=(value*31+code)&0xffffffff
    return COLORS[value%len(COLORS)]

def _font(size,bold=False):
    paths=(["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf","C:/Windows/Fonts/arialbd.ttf"] if bold else
           ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","C:/Windows/Fonts/arial.ttf"])
    for path in paths:
        try:return ImageFont.truetype(path,size)
        except OSError:pass
    return ImageFont.load_default()

def _mix(color,background,amount=.13):
    parts=lambda s:[int(s[i:i+2],16) for i in (1,3,5)]
    return '#'+''.join(f'{round(a*amount+b*(1-amount)):02x}' for a,b in zip(parts(color),parts(background)))

def _wrap(text,width,size,bold=False):
    font=_font(size,bold);lines=[];line=''
    for word in str(text).split():
        candidate=(line+' '+word).strip()
        if font.getlength(candidate)<=width:line=candidate;continue
        if line:lines.append(line);line=''
        for char in word:
            if line and font.getlength(line+char)>width:lines.append(line);line=''
            line+=char
    if line:lines.append(line)
    return lines or ['']

def _layout(start,end,category,theme):
    if theme not in THEMES:raise ValueError('Unknown theme')
    data=snapshot(start,end,category)
    all_days=data['days'];single=len(all_days)==1
    weekends=any(date.fromisoformat(d['date']).weekday()>=5 and (d['tasks'] or d['activity']) for d in all_days)
    cols=1 if single else 7 if weekends else 5
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    week_start=(data.get('week_start',1)+6)%7
    begin=first if single else first-timedelta(days=(first.weekday()-week_start+7)%7)
    finish=last if single else last+timedelta(days=6-(last.weekday()-week_start+7)%7)
    by_date={d['date']:d for d in all_days};cells=[];cursor=begin
    width=1100;cw=width/cols
    while cursor<=finish:
        if cols!=5 or cursor.weekday()<5:
            day=by_date.get(cursor.isoformat());items=[]
            if day:
                for task in day['tasks']:
                    cats=task['categories'];lines=_wrap(task['title'],cw-28,12,True)
                    labels=[(c,_wrap(c,cw-39,10)) for c in cats]
                    label=task.get('schedule_label','')
                    height=12+len(lines)*16+sum(len(parts)*13+2 for _,parts in labels)+(14 if label else 0)
                    items.append({'lines':lines,'labels':labels,'height':height,'color':category_color(cats[0]),'activity':False,'schedule_label':label})
                for event in day['activity']:
                    cats=event['categories'];lines=_wrap(event['body'],cw-28,12)
                    labels=[(c,_wrap(c,cw-39,10)) for c in cats]
                    height=26+len(lines)*16+sum(len(parts)*13+2 for _,parts in labels)
                    items.append({'lines':lines,'labels':labels,'height':height,'color':category_color(cats[0]),'activity':True,'kind':event['kind']})
            cells.append({'date':cursor,'outside':day is None,'items':items})
        cursor+=timedelta(days=1)
    rows=[cells[i:i+cols] for i in range(0,len(cells),cols)]
    heights=[max(86,max((29+sum(t['height']+4 for t in c['items']) for c in row),default=0)) for row in rows]
    top=39+(27 if cols>1 else 0)
    return data,cols,rows,heights,width,top+sum(heights)+1

def _draw(start,end,category,theme,rect,text,layout=None):
    data,cols,rows,heights,width,height=layout or _layout(start,end,category,theme)
    bg,ink,surface=THEMES[theme];cw=width/cols
    rect(0,0,width,height,bg)
    label=start if start==end else f'{start} – {end}'
    text(10,12,label,13,ink,True)
    y=39
    if cols>1:
        rect(0,y,width,27,surface)
        for i,name in enumerate([['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][(d+(data.get('week_start',1)+6)%7)%7] for d in range(7) if cols==7 or (d+(data.get('week_start',1)+6)%7)%7<5]):text(i*cw+8,y+8,name,11,ink,False)
        y+=27
    for row,rh in zip(rows,heights):
        for i,cell in enumerate(row):
            x=i*cw
            rect(x,y,cw-1,rh-1,surface if cell['outside'] else bg)
            rect(x+cw-1,y,1,rh,surface)
            text(x+8,y+7,str(cell['date'].day),11,ink,False)
            ty=y+27
            for item in cell['items']:
                rect(x+5,ty,cw-10,item['height'],_mix(item['color'],bg),3)
                line_y=ty+6
                if item['activity'] or item.get('schedule_label'):text(x+11,line_y,item['kind'] if item['activity'] else item['schedule_label'],10,ink,False);line_y+=14
                for line in item['lines']:text(x+11,line_y,line,12,ink,not item['activity']);line_y+=16
                for cat,parts in item['labels']:
                    for line in parts:text(x+11,line_y,line,10,ink,False);line_y+=13
                    line_y+=2
                ty+=item['height']+4
        rect(0,y+rh-1,width,1,surface)
        y+=rh
    return width,height

def png(start,end,category='',theme='sage',scale=2):
    if scale not in (1,2,4):raise ValueError('Scale must be 1, 2, or 4')
    layout=_layout(start,end,category,theme)
    *_,width,height=layout
    image=Image.new('RGB',(width*scale,height*scale));draw=ImageDraw.Draw(image)
    def rect(x,y,w,h,fill,radius=0):
        box=tuple(round(v*scale) for v in (x,y,x+w,y+h))
        draw.rounded_rectangle(box,radius=radius*scale,fill=fill)
    def text(x,y,label,size,color,bold):
        draw.text((round(x*scale),round(y*scale)),label,font=_font(size*scale,bold),fill=color,anchor='lt')
    _draw(start,end,category,theme,rect,text,layout)
    output=BytesIO();image.save(output,format='PNG',optimize=True)
    return output.getvalue()

def svg(start,end,category='',theme='sage'):
    elements=[]
    def rect(x,y,w,h,fill,radius=0):
        elements.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{radius:g}" fill="{fill}"/>')
    def text(x,y,label,size,color,bold):
        elements.append(f'<text x="{x:g}" y="{y:g}" dy="{size*.82:g}" font-family="DejaVu Sans,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(str(label))}</text>')
    width,height=_draw(start,end,category,theme,rect,text)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><title>{escape(start)} – {escape(end)}</title>'+''.join(elements)+'</svg>'
