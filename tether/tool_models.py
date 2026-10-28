"""Only list models with known chat-completions tool support."""
from functools import lru_cache
import json
from pathlib import Path
import re
from datetime import date
from urllib.parse import urlparse

@lru_cache(maxsize=1)
def catalog():return json.loads(Path(__file__).with_name('tool-models.json').read_text(encoding='utf-8'))

def base_id(id):return re.sub(r'-\d{4}-\d{2}-\d{2}$','',id.split(':')[1] if id.startswith('ft:') and ':' in id[3:] else id)

def options(base,id):return catalog()['openai'].get(base_id(id),{}) if urlparse(base).hostname=='api.openai.com' else {}

def compatible_models(items,base):
    result=[]
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'].strip() or len(item['id'])>200:continue
        id=item['id'];caps=item.get('capabilities') if isinstance(item.get('capabilities'),dict) else {}
        flags=[item.get('supports_tool_calling'),item.get('supports_function_calling'),caps.get('tools'),caps.get('tool_calling'),caps.get('function_calling')]
        if any(value is False for value in flags):continue
        if isinstance(item.get('shutdown_date'),str) and item['shutdown_date']<=date.today().isoformat():continue
        if re.search(r'embed|whisper|tts|audio|realtime|transcrib|moderation|dall-e|image|video|sora',id,re.I):continue
        parameters=item.get('supported_parameters')
        if isinstance(parameters,list) and not any(value in parameters for value in ('tools','function_calling')):continue
        if urlparse(base).hostname=='api.openai.com':supported=base_id(id) in catalog()['openai']
        else:supported=base_id(id) in catalog()['openai'] or any(value is True for value in flags) or isinstance(parameters,list) and any(value in parameters for value in ('tools','function_calling'))
        if supported:result.append(id)
    return sorted(set(result))
