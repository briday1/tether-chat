"""Transcribe a user-started microphone recording with their configured provider."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener
from uuid import uuid4
import os

MAX_AUDIO = 20 * 1024 * 1024
TYPES = {'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/ogg': 'ogg', 'audio/wav': 'wav',
         'audio/x-wav': 'wav', 'audio/mpeg': 'mp3', 'audio/x-m4a': 'm4a'}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


# Keep the user's credential and recording pinned to the configured endpoint.
urlopen = build_opener(_NoRedirect()).open


def transcribe(audio, content_type, model='whisper-1', expected_base=None):
    from . import ai, secrets
    kind = (content_type or '').split(';', 1)[0].strip().lower()
    if kind not in TYPES or not audio or len(audio) > MAX_AUDIO:
        raise ValueError('Use a supported audio recording between 1 byte and 20 MB')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}', model):
        raise ValueError('Enter a valid provider transcription model in Voice input settings')
    config = ai.load()
    base = (os.environ.get('TEND_AI_BASE_URL') or config.get('base_url') or 'https://api.openai.com/v1').rstrip('/')
    parsed = urlparse(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('The transcription provider URL must use HTTPS')
    if expected_base and expected_base.rstrip('/') != base:
        raise ValueError('Your provider changed during recording. Record again for the new provider.')
    key = secrets.get()
    if not key:
        raise ValueError('Configure your API key in Settings before using provider transcription')
    boundary = 'tether-' + uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.{TYPES[kind]}"\r\n'
            f'Content-Type: {kind}\r\n\r\n').encode() + audio + f'\r\n--{boundary}--\r\n'.encode()
    request = Request(base + '/audio/transcriptions', data=body, method='POST',
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise ValueError(f'Transcription provider returned HTTP {exc.code}. Check its audio/transcriptions support, model, key, and quota.') from None
    except (URLError, TimeoutError, OSError):
        raise ValueError('Could not finish transcription. Check your provider connection. The recording was not retried.') from None
    except (ValueError, TypeError):
        raise ValueError('The provider returned an unsupported transcription response') from None
    text = result.get('text') if isinstance(result, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValueError('No speech was recognized in the recording')
    return {'text': text.strip()}
