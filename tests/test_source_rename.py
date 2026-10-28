"""Source naming must not orphan existing user data or shortcuts."""
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def test_source_package_and_entrypoints_are_tether():
    assert (ROOT / 'tether' / '__init__.py').is_file()
    assert not (ROOT / 'tend').exists()
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    project = config['project']
    assert project['name'] == 'tether-chat'
    assert project['scripts'] == {'tether-chat': 'tether.cli:main'}
    assert project['gui-scripts'] == {'tether-chat-desktop': 'tether.native:main'}

def test_legacy_shortcut_module_still_launches():
    result = subprocess.run([sys.executable, '-m', 'tend.cli', '--help'], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'tether-chat' in result.stdout

def test_existing_data_and_keyring_identifiers_unchanged(monkeypatch, tmp_path):
    from tether import storage, secrets
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert storage.active_path() == tmp_path / '.tend' / 'tend.sqlite3'
    assert secrets.SERVICE == 'tend-local-assistant'
    assert "'tend-ui-theme'" in (ROOT / 'tether/theme.js').read_text()

def test_new_environment_names_prefer_and_legacy_names_work(monkeypatch):
    from tether import environment, ports
    monkeypatch.delenv('TETHER_WEB_PORT', raising=False)
    monkeypatch.setenv('TEND_WEB_PORT', '8877')
    assert ports.web_port() == 8877
    assert environment.snapshot()['TETHER_WEB_PORT'] == '8877'
    monkeypatch.setenv('TETHER_WEB_PORT', '9988')
    assert ports.web_port() == 9988
    assert environment.snapshot()['TETHER_WEB_PORT'] == '9988'
