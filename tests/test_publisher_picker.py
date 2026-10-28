"""Publisher-only build configuration must not log key values or alter OAuth IDs."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def run_config(tmp_path, key):
    path=tmp_path/'config.json'
    original={'clientId':'public-client.apps.googleusercontent.com','projectNumber':'123','pickerKey':''}
    path.write_text(json.dumps(original))
    env=os.environ.copy();env.pop('TETHER_GOOGLE_PICKER_API_KEY',None)
    if key is not None:env['TETHER_GOOGLE_PICKER_API_KEY']=key
    result=subprocess.run([sys.executable,str(ROOT/'scripts/configure_google_picker.py'),'--config',str(path)],env=env,text=True,capture_output=True)
    return result,json.loads(path.read_text()),original

def test_public_key_injection_preserves_ids_without_logging(tmp_path):
    key='synthetic-picker-key-not-real'
    result,config,original=run_config(tmp_path,key)
    assert result.returncode==0
    assert config==dict(original,pickerKey=key)
    assert key not in result.stdout+result.stderr

def test_absent_key_fails_closed_without_modifying_config(tmp_path):
    result,config,original=run_config(tmp_path,None)
    assert result.returncode==1 and config==original

def test_client_secret_is_rejected_without_logging(tmp_path):
    value='GOCSPX-synthetic-not-a-real-secret'
    result,config,original=run_config(tmp_path,value)
    assert result.returncode==1 and config==original
    assert value not in result.stdout+result.stderr

def test_pr_workflow_has_no_secret_before_tests():
    text=(ROOT/'.github/workflows/web-pages.yml').read_text()
    pos=text.index('      - name: Configure approved public Google Picker key')
    assert "github.event_name != 'pull_request'" in text[pos:text.index('      - name: Build the GitHub Pages edition')]
    assert 'secrets.TETHER_GOOGLE_PICKER_API_KEY' not in text[:pos]


def test_desktop_release_never_receives_picker_key():
    text=(ROOT/'.github/workflows/publish-pypi.yml').read_text()
    assert 'TETHER_GOOGLE_PICKER_API_KEY' not in text
    assert 'configure_google_picker.py' not in text

def test_publisher_default_targets_browser_only():
    text=(ROOT/'scripts/configure_google_picker.py').read_text()
    assert "ROOT/'web/drive-config.json'" in text
