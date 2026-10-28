"""The browser legal entry point must not change desktop or policy URLs."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('about_build',ROOT/'scripts/build_web.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
def test_browser_about_is_scoped_and_footer_is_removed(tmp_path):
    output=builder.build(tmp_path/'web','/tether-chat/')
    shell=(output/'index.html').read_text(encoding='utf-8')
    assert '<footer id="legal">' not in shell
    assert ' - 30px' not in shell
    for page in ['conversation.html','board.html','display.html']:
        assert 'src="/tether-chat/about.mjs"' in (output/page).read_text(encoding='utf-8')
    about=(output/'about.mjs').read_text(encoding='utf-8')
    for required in ['showModal()',"'aria-labelledby'", "'aria-haspopup'",'trigger.focus()',"'Privacy policy','privacy.html'","'Terms of service','terms.html'",'TETHER_CONFIG?.version']:
        assert required in about
    for page in ['index.html','board.html','display.html']:
        assert 'about.mjs' not in (ROOT/'tether'/page).read_text(encoding='utf-8')
