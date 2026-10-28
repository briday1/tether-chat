"""Actionable provider errors and retry delays shared by desktop requests."""
import json
import math
import random
import re
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse


def normalize_base(value):
    base=value.strip().rstrip('/')
    p=urlparse(base)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('Use an HTTPS provider base URL without credentials, a query, or a fragment')
    return base


def retry_delay(header,attempt=0):
    if header and header.strip():
        try:
            seconds=float(header)
            if math.isfinite(seconds):return max(0,seconds)
        except ValueError:
            try:return max(0,parsedate_to_datetime(header).timestamp()-time.time())
            except (ValueError,TypeError,OverflowError):pass
    return 2**attempt+random.uniform(0,.3)


def failure(status,body,key='',base=''):
    try:error=json.loads(body).get('error',{})
    except (ValueError,TypeError,AttributeError):error={}
    if not isinstance(error,dict):error={}
    code=error.get('code') if isinstance(error.get('code'),str) else ''
    raw=error.get('message') if isinstance(error.get('message'),str) else ''
    billing={
        'credit_balance_exhausted':'Your API credit balance is empty. Add credits in your provider billing settings.',
        'organization_spend_limit_exceeded':'Your organization API spending limit was reached. Check its billing limits.',
        'project_spend_limit_exceeded':'Your project API spending limit was reached. Check the project limits.',
        'organization_usage_limit_exceeded':'Your organization API usage limit was reached. Check your provider usage limits.',
    }
    quota=code in billing or code in {'insufficient_quota','billing_hard_limit_reached','billing_not_active','usage_limit_reached'} or error.get('type')=='insufficient_quota' or bool(re.search(r'exceeded your current quota|insufficient (?:credit|quota)|credit balance|billing hard limit',raw,re.I))
    message=billing.get(code)
    if not message and quota:message='Your API billing or usage quota was reached. Check API credits and project limits; creating a key does not add credit.'
    if message and urlparse(base).hostname=='api.openai.com':message+=' ChatGPT subscriptions do not include API credit.'
    if not message:message={
        401:'The provider rejected this API key. Check the key and provider URL.',
        403:'The provider denied access. Check key permissions and model access.',
        404:'The API endpoint or model was not found. Check the provider base URL and model.',
        429:'The provider temporarily rate limited this connection. Wait before trying again.',
    }.get(status)
    if not message:
        detail=raw.replace(key,'[redacted]') if key else raw
        detail=re.sub(r'\bsk-[a-zA-Z0-9_-]+','[redacted]',detail)
        detail=re.sub(r'[\x00-\x1f]',' ',detail)[:240]
        message='The AI provider rejected the request.'+(' '+detail if detail else ' Check the provider URL and selected model.')
    safe_code=code if re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',code) and not (key and key in code) and not code.startswith('sk-') else ''
    return message+f' (HTTP {status}'+(', '+safe_code if safe_code else '')+')', not quota and status in {429,500,502,503,504}
