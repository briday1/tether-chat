from pathlib import Path
import importlib.util
import re
import tomllib

ROOT=Path(__file__).resolve().parents[1]

def test_year_sequence_and_bump():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert re.fullmatch(r'20\d{2}\.[1-9]\d*',project['version'])
    spec=importlib.util.spec_from_file_location('bump',ROOT/'scripts/bump_version.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.next_version('0.2.2',2026)=='2026.1'
    assert module.next_version('2026.1',2026)=='2026.2'
    assert module.next_version('2026.10',2027)=='2027.1'

def test_readme_order_and_desktop_only_gallery():
    text=(ROOT/'README.md').read_text(encoding='utf-8')
    before=text.split('## Install')[0]
    # Count the lead application screenshot, independently of package badges.
    assert len(re.findall(r'^!\[',before,re.M))==1
    assert text.index('## Set up and use')<text.index('## More screenshots')
    assert not re.search(r'(?:!\[.*?\]\([^)]*mobile[^)]*\)|<img[^>]*mobile)',text,re.I)
    assert '2026.1' in text and '2026.2' in text
