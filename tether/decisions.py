"""Persistent reminder defaults and conservative task reuse for assistant operations."""
import calendar
from datetime import datetime,timedelta,timezone
import re
import unicodedata

DEFAULT_PREFERENCES={'week_start':1,'morning_time':'09:00','night_time':'21:00'}
DAYS=['sunday','monday','tuesday','wednesday','thursday','friday','saturday']

def preferences(value=None):
    value={} if value is None else value
    if not isinstance(value,dict) or set(value)-set(DEFAULT_PREFERENCES):raise ValueError('Unknown reminder preference')
    result={**DEFAULT_PREFERENCES,**value}
    if type(result['week_start']) is not int or not 0<=result['week_start']<=6:raise ValueError('Choose a beginning-of-week reminder day')
    for key in ('morning_time','night_time'):
        if not isinstance(result[key],str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',result[key]):raise ValueError('Use a time in HH:MM format')
    return result

def resolve_reminder(value,saved=None,reference=None):
    if value is None or value=='':return None
    if not isinstance(value,str):raise ValueError('Use a reminder date or a period such as next week')
    p=preferences(saved);now=reference or datetime.now().astimezone();zone=reference.tzinfo if reference is not None else None;text=value.strip().lower()
    clock=p['night_time'] if re.search(r'\b(night|tonight)\b',text) else '18:00' if re.search(r'\bevening\b',text) else '13:00' if re.search(r'\bafternoon\b',text) else '12:00' if re.search(r'\bnoon\b',text) else p['morning_time']
    explicit=re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',text) or re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\b',text) or re.search(r'\b(\d{1,2}):(\d{2})\b',text)
    if explicit:
        hour=int(explicit[1]);minute=int(explicit[2] or 0)
        if len(explicit.groups())>2 and explicit[3]:hour=hour%12+(12 if explicit[3]=='pm' else 0)
        if hour>23 or minute>59:raise ValueError('Invalid reminder time')
        clock=f'{hour:02}:{minute:02}'
    hour,minute=map(int,clock.split(':'))
    def wall(year,month,day):return datetime(year,month,day,hour,minute,tzinfo=zone).astimezone()
    def day(offset=0):
        date=now.date()+timedelta(days=offset);return wall(date.year,date.month,date.day)
    def month(offset,first=False):
        index=now.year*12+now.month-1+offset;year,number=divmod(index,12);number+=1
        return wall(year,number,1 if first else min(now.day,calendar.monthrange(year,number)[1]))
    if re.fullmatch(r'\d{4}-\d\d-\d\d',text):
        year,number,date=map(int,text.split('-'));return wall(year,number,date).astimezone(timezone.utc).isoformat()
    if re.match(r'\d{4}-\d\d-\d\dT',value.strip(),re.I):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
    explicit_day=re.search(r'\b\d{4}-\d\d-\d\d\b',text)
    if explicit_day:
        year,number,date=map(int,explicit_day[0].split('-'));return wall(year,number,date).astimezone(timezone.utc).isoformat()
    weekday=next((i for i,name in enumerate(DAYS) if re.search(r'\b'+name+r'\b',text)),None)
    relative=re.search(r'\bin\s+(a|an|one|two|three|four|\d+)\s+(minute|hour|day|week|month|year)s?\b',text)
    if relative:
        amount={'a':1,'an':1,'one':1,'two':2,'three':3,'four':4}.get(relative[1]);amount=amount if amount is not None else int(relative[1]);unit=relative[2]
        if not 1<=amount<=1000:raise ValueError('Use a reminder interval from 1 to 1000')
        if unit in ('minute','hour'):return (now+timedelta(seconds=amount*(3600 if unit=='hour' else 60))).astimezone(timezone.utc).isoformat()
        date=day(amount*(7 if unit=='week' else 1)) if unit in ('day','week') else month(amount*(12 if unit=='year' else 1))
    elif re.search(r'\btomorrow\b|\bnext day\b',text) or text=='day':date=day(1)
    elif re.search(r'\b(next|this) week\b',text) or text=='week':
        # Explicit weekdays use the fixed Sunday–Saturday calendar, not the reminder default.
        date=day(-((now.weekday()+1)%7)+(0 if 'this week' in text else 7)+weekday) if weekday is not None else day(-(((now.weekday()+1)%7-p['week_start']+7)%7)+(0 if 'this week' in text else 7))
    elif re.search(r'\b(next|this) month\b',text) or text=='month':date=month(0 if 'this month' in text else 1,True)
    elif re.search(r'\b(next|this) year\b',text) or text=='year':date=wall(now.year+(0 if 'this year' in text else 1),1,1)
    else:
        if weekday is not None:
            offset=(weekday-(now.weekday()+1)%7+7)%7
            if offset==0 and re.search(r'\bnext\b',text):offset=7
            date=day(offset)
            if date<=now:date=day(offset+7)
        elif re.search(r'\b(today|morning|night|tonight|evening|afternoon|soon)\b',text):date=day()
        else:raise ValueError('Use a date or a period such as tomorrow, next week, next month, or next year')
    if date<=now:date=day(1)
    return date.astimezone(timezone.utc).isoformat()

def recurring_intent(text):
    """Do not turn an explicitly repeating request into a one-shot reminder."""
    return bool(re.search(r'\b(daily|weekly|monthly|quarterly|yearly|annually|every\s+(?:day|week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|repeat(?:ing)?)\b', text, re.I))

def reminder_intent(text):
    if not re.search(r'\b(remind|reminder|bring.{0,12}attention|follow up|check back)\b',text,re.I):return None
    if re.search(r'\b\d{4}-\d\d-\d\d\b',text):return text
    if re.search(r'\b(?:next|this) week\b',text,re.I) and any(re.search(r'\b'+name+r'\b',text,re.I) for name in DAYS):return text
    for pattern in (r'\bin\s+(?:a|an|one|two|three|four|\d+)\s+(?:minute|hour|day|week|month|year)s?(?:\s+(?:in the )?(?:morning|night|evening|afternoon))?(?:\s+at\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?',r'\b(?:next|this)\s+(?:day|week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+(?:in the )?(?:morning|night|evening|afternoon))?(?:\s+at\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?',r'\b(?:today|tomorrow|tonight)(?:\s+(?:in the )?(?:morning|night|evening|afternoon))?(?:\s+at\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?'):
        found=re.search(pattern,text,re.I)
        if found:return found[0]
    return None

def decision_followup(text):return bool(re.search(r'^(?:(?:please|just|ok|okay|then)\s+)*(?:figure (?:it|that) out|use your (?:best )?judg(?:e)?ment|you (?:decide|choose|pick)|pick (?:one|a day|a time|a category)|do (?:it|that)|go ahead|make it\b|put it\b|move it\b|change it\b|schedule it\b|yes\b)',text.strip(),re.I))

def task_key(title):
    text=unicodedata.normalize('NFKC',title).casefold();text=text.replace('_',' ');text=re.sub(r'\bdental\b','dentist',text);text=re.sub(r'\bappt\b','appointment',text)
    words=re.sub(r'[^\w\s]',' ',text).split();skip={'a','an','the','my','me','to','please','remind','reminder','make','book','schedule'}
    return ' '.join(sorted(word for word in words if word not in skip))

def choose_categories(title,summary,available,supplied=None):
    canonical={name.casefold():name for name in available if name.casefold()!='unsorted'}
    chosen=[canonical.get(name.strip().casefold(),name.strip()) for name in (supplied or []) if isinstance(name,str) and name.strip() and name.strip().casefold()!='unsorted']
    if chosen:return list(dict.fromkeys(chosen))
    text=title+' '+summary
    groups=[(r'\b(dentist|dental|doctor|medical|health|prescription|pharmacy|therapy|checkup)\b','Health',['health','medical','healthcare','wellness','personal']),
      (r'\b(computer|software|server|laptop|network|printer|technical)\b','Technology',['technology','it','tech','work']),
      (r'\b(bill|tax|bank|budget|payment|finance)\b','Finance',['finance','finances','money','personal']),
      (r'\b(house|home|repair|laundry|clean|groceries|garden)\b','Home',['home','household','errands','personal']),
      (r'\b(project|report|briefing|team|client|work|meeting)\b','Work',['work','projects','business'])]
    for pattern,fallback,aliases in groups:
        if re.search(pattern,text,re.I):return [next((canonical[name] for name in aliases if name in canonical),fallback)]
    for name,value in canonical.items():
        if len(name)>3 and name in text.casefold():return [value]
    return [canonical.get('personal','Personal')]
