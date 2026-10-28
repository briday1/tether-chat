"""Inject the publisher's restricted browser key into a release build, never logs.

This key is public in the resulting app. Only use a website/API-restricted Picker
key explicitly approved for publication. Do not supply an OAuth client secret.
"""
from pathlib import Path
import argparse
import json
import os

ROOT = Path(__file__).resolve().parents[1]

def configure(path):
    key = os.environ.get('TETHER_GOOGLE_PICKER_API_KEY', '').strip()
    if not key:
        raise ValueError('TETHER_GOOGLE_PICKER_API_KEY is missing; release configuration was not changed')
    if any(character.isspace() for character in key) or key.startswith('GOCSPX-'):
        raise ValueError('Expected a restricted browser API key, not an OAuth secret')
    config = json.loads(path.read_text(encoding='utf-8'))
    if not config.get('clientId') or not config.get('projectNumber'):
        raise ValueError('Public OAuth client ID and project number must be configured first')
    config['pickerKey'] = key
    path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'web/drive-config.json')
    args = parser.parse_args()
    try:
        configure(args.config)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error)+'\n')
    print('Configured the approved public Picker key for this build.')

if __name__ == '__main__':
    main()
