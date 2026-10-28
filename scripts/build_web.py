"""Build the browser edition from the desktop screens without modifying the desktop package."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def shared_ai():
    """Extract only the public prompt and tool declarations; never load provider settings."""
    source = ast.parse((ROOT / 'tether/ai.py').read_text(encoding='utf-8'))
    nodes = [node for node in source.body if
             isinstance(node, ast.FunctionDef) and node.name == 'spec' or
             isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'S', 'TOOLS', 'SYSTEM'} for t in node.targets)]
    namespace = {'__builtins__': {'list': list}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'public-ai-declarations', 'exec'), namespace)
    return namespace['TOOLS'], namespace['SYSTEM']


def paths(text, base):
    # api('/board') is an endpoint suffix, whereas '/board#task/…' is a
    # navigation URL. Protect the former before making Pages navigation explicit.
    text = text.replace("api('/board')", "api('__TETHER_BOARD_API__')").replace('api("/board")', 'api("__TETHER_BOARD_API__")')
    for old, new in [('/drive-sharing.mjs',base+'drive-sharing.mjs'), ('/drive-sharing',base+'drive-sharing.html'), ('/board', base + 'board.html'), ('/workspace.js', base + 'workspace.js'), ('/display.js', base + 'display.js'), ('/display.css', base + 'display.css'), ('/snapshots', base + 'snapshots.html'),
                     ('/api', base + 'api'), ('/icon/', base + 'icon/'),
                     ('/theme.css', base + 'theme.css'), ('/theme.js', base + 'theme.js'),
                     ('/chat.js', base + 'chat.js'), ('/action-notes.js', base + 'action-notes.js'),
                     ('/voice.js', base + 'voice.js'),
                     ('/provider-models.js', base + 'provider-models.js'),
                     ('/preferences.js', base + 'preferences.js'),
                     ('/locations.js', base + 'locations.js'),
                     ('/updates.js', base + 'updates.js'),
                     ('/notes.js', base + 'notes.js'), ('/notes.css', base + 'notes.css'),
                     ('/favicon.svg', base + 'favicon.svg'), ('/manifest.webmanifest', base + 'manifest.webmanifest')]:
        for quote in ('"', "'"):
            text = text.replace(quote + old, quote + new)
    text = re.sub(r'''(["'])/display(?=["'?#])''', lambda m:m[1]+base+'display.html', text)
    text = text.replace('href="/"', 'href="' + base + 'conversation.html"')
    text = text.replace("'/?task_context=", "'" + base + 'conversation.html?task_context=')
    text = text.replace("'/?discuss=", "'" + base + 'conversation.html?discuss=')
    text = text.replace('__TETHER_BOARD_API__', '/board')
    return text


def screen(name, base):
    page = (ROOT / ('web' if name=='drive-sharing.html' else 'tether') / name).read_text(encoding='utf-8')
    if name not in ('snapshot.html','display.html','drive-sharing.html'):
        page, changed = re.subn(r'<h2>AI connection</h2>.*?<a href="/api/backup"[^>]*>Download SQLite backup</a>',
                               lambda _: (ROOT / 'web/sharing-settings.html').read_text(encoding='utf-8') + (ROOT / 'web/settings.html').read_text(encoding='utf-8'), page, flags=re.S)
        if changed != 1:
            raise ValueError('Desktop settings changed; update the browser settings adapter for ' + name)
        page = page.replace('</body>', '<script type="module" src="./drive-sharing.mjs"></script></body>')
        start = page.index('async function loadSettings(){')
        end = page.index('function navigateBoardHash(){', start) if name == 'board.html' else page.index('</script>', start)
        page = page[:start] + 'const loadSettings=window.tetherLoadSettings,loadStorage=window.tetherLoadStorage;\n' + page[end:]
    elif name == 'snapshot.html':
        page, changed = re.subn(r'function download\(format\)\{.*?\n\}',
                               'function download(format){window.tetherExportCalendar(last,format)}', page, flags=re.S)
        if changed != 1:
            raise ValueError('Desktop calendar download changed; update its browser adapter')
        page = page.replace('</html>', '<script type="module" src="./calendar-export.mjs"></script></html>')
    page = paths(page, base)
    page = re.sub(r'<title>.*?</title>', '<title>tether-home · tether</title>', page, count=1)
    # Product labels change, but legacy browser storage keys stay stable.
    bridge = f'<script src="{base}app-config.js"></script><script src="{base}bridge.js"></script><link rel="stylesheet" href="{base}browser.css">'
    # Place the bridge before every screen script, including synchronous calendar scripts.
    page = page.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + bridge, 1)
    # Load browser adjustments after the shared screen styles.
    if '</head>' in page:
        page = page.replace('</head>', f'<link rel="stylesheet" href="{base}browser.css"></head>', 1)
    # Browser storage must not collide with a desktop server on the same origin.
    page = page.replace("'tether-chat-outbox'", repr('tether-web-outbox:' + base))
    page = page.replace("'tether-chat-draft'", repr('tether-web-draft:' + base))
    return page


def build(output, base='/'):
    if not re.fullmatch(r'/(?:[A-Za-z0-9_.-]+/)*', base) or '..' in base.split('/'):
        raise ValueError('Base path must be / or a repository path such as /tether-chat/')
    output = Path(output).resolve()
    if output == ROOT or output in ROOT.parents or output == ROOT / 'web' or output == ROOT / 'tether':
        raise ValueError('Choose a separate generated output folder')
    marker = output / '.tether-web-build'
    if output.exists() and any(output.iterdir()) and not marker.exists():
        raise ValueError('Refusing to replace a folder that is not a tether web build')
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    marker.write_text('Generated browser edition; do not edit.\n', encoding='utf-8')
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    tools, system = shared_ai()
    config = {'version': version, 'base': base, 'product':'tether-home', 'workspace':'home', 'tools': tools, 'system': system,
              'tool_models':json.loads((ROOT/'tether/tool-models.json').read_text(encoding='utf-8'))}
    # The spaced assignment also makes legacy in-session pollers ignore this
    # release; only a new launch should switch an already-open older app.
    (output / 'app-config.js').write_text('window.TETHER_CONFIG = ' + json.dumps(config, ensure_ascii=True) + ';\n', encoding='utf-8')
    for source in (ROOT / 'web').iterdir():
        if source.suffix in {'.js', '.mjs', '.css'} or source.name in {'index.html', 'privacy.html', 'terms.html'}:
            shutil.copy2(source, output / source.name)
    # Keep recovery independent of cached scripts, styles and app configuration.
    (output/'update.html').write_text((ROOT/'web/update.html').read_text(encoding='utf-8').replace('__VERSION__',version),encoding='utf-8')
    for name in ('theme.css', 'theme.js', 'favicon.svg', 'action-notes.js', 'chat.js', 'voice.js', 'speech.mjs', 'updates.js', 'notes.js', 'notes.css', 'provider-models.js', 'preferences.js', 'locations.js', 'display.js', 'display.css'):
        text = paths((ROOT / 'tether' / name).read_text(encoding='utf-8'), base)
        if name == 'chat.js':
            text = text.replace("'tether-chat-outbox'", repr('tether-web-outbox:' + base)).replace("'tether-chat-draft'", repr('tether-web-draft:' + base))
        (output / name).write_text(text, encoding='utf-8')
    shutil.copy2(ROOT/'web/drive-config.json',output/'drive-config.json')
    for original, target in [('index.html','conversation.html'),('board.html','board.html'),('snapshot.html','snapshots.html'),('display.html','display.html'),('drive-sharing.html','drive-sharing.html')]:
        (output / target).write_text(screen(original, base), encoding='utf-8')
    sys.path.insert(0, str(ROOT))
    from tether.windows_icon import raster
    (output / 'icon').mkdir()
    for size in (32,192,512): (output / f'icon/{size}.png').write_bytes(raster(size))
    manifest = {'id':base,'name':'tether-home','short_name':'tether-home','description':'Home tasks and household sharing by tether',
                'start_url':base,'scope':base,'display':'standalone','background_color':'#f6f7f3','theme_color':'#f6f7f3',
                'icons':[{'src':base+f'icon/{size}.png','sizes':f'{size}x{size}','type':'image/png','purpose':'any'} for size in (192,512)]}
    (output / 'manifest.webmanifest').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / '.nojekyll').touch()
    assets = sorted(base + str(file.relative_to(output)).replace('\\', '/') for file in output.rglob('*') if file.is_file() and not file.name.startswith('.') and file.name!='update.html')
    digest = hashlib.sha256(b''.join(file.read_bytes() for file in sorted(output.rglob('*')) if file.is_file())).hexdigest()[:16]
    worker = (ROOT / 'web/sw.js.in').read_text(encoding='utf-8')
    worker = worker.replace('__CACHE__', json.dumps(f'tether-web:{base}:{version}:{digest}')).replace('__PREFIX__', json.dumps('tether-web:' + base + ':'))
    worker = worker.replace('__ASSETS__', json.dumps(assets)).replace('__BASE__', json.dumps(base)).replace('__VERSION__', json.dumps(version))
    (output / 'sw.js').write_text(worker, encoding='utf-8')
    print(f'Built tether-home {version} browser edition at {output} (base {base})')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'web-dist')
    parser.add_argument('--base-path', default='/')
    args = parser.parse_args()
    build(args.output, args.base_path)
