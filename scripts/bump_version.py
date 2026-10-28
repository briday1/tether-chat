"""Bump a main release as YYYY.sequence; keep metadata and runtime version equal."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def next_version(current, year):
    match = re.fullmatch(r'(\d{4})\.([1-9]\d*)', current)
    if match and int(match[1]) > year:
        raise ValueError('The current version is already in a later year')
    number = int(match[2])+1 if match and int(match[1]) == year else 1
    return f'{year}.{number}'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=datetime.now(timezone.utc).year)
    args = parser.parse_args()
    if not 2000 <= args.year <= 9999:
        parser.error('Year must be a four-digit year')
    meta = ROOT/'pyproject.toml'; runtime = ROOT/'tether/__init__.py'
    text = meta.read_text(encoding='utf-8')
    old = tomllib.loads(text)['project']['version']; new = next_version(old, args.year)
    code = runtime.read_text(encoding='utf-8')
    if f'__version__ = "{old}"' not in code:
        raise SystemExit('Runtime and distribution versions do not match; nothing changed')
    meta.write_text(text.replace(f'version = "{old}"', f'version = "{new}"', 1), encoding='utf-8')
    runtime.write_text(code.replace(f'__version__ = "{old}"', f'__version__ = "{new}"', 1), encoding='utf-8')
    print(f'{old} -> {new}. Commit both files to main to start the tested release pipeline.')

if __name__ == '__main__':
    main()
