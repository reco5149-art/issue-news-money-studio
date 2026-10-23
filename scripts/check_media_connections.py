"""Verify Typecast/KIE credentials without generating paid media or printing secrets."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def check(name, key, url, header):
    result = {'service': name, 'authenticated': False}
    if not key:
        return {**result, 'error': 'missing_key'}
    try:
        with httpx.Client(timeout=30, trust_env=False) as client:
            response = client.get(url, headers=header(key.strip()))
        result['http_status'] = response.status_code
        if response.status_code != 200:
            return {**result, 'error': 'authentication_or_service_error'}
        data = response.json()
        if name == 'KIE AI':
            result['api_code'] = data.get('code')
            result['authenticated'] = data.get('code') == 200
            if result['authenticated'] and isinstance(data.get('data'), (int, float)):
                result['credits'] = data['data']
        else:
            voices = data if isinstance(data, list) else data.get('voices', data.get('data'))
            result['authenticated'] = isinstance(voices, list)
            if result['authenticated']:
                result['voice_count'] = len(voices)
            else:
                result['error'] = 'unexpected_response'
    except (httpx.HTTPError, ValueError, AttributeError):
        result['error'] = 'connection_or_response_error'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Save verified keys to project .env')
    args = parser.parse_args()
    values = dotenv_values(ROOT / '.env')
    values.update({k: v for k, v in dotenv_values(ROOT / 'data/external-api-keys.env').items() if v})
    specs = [
        ('Typecast', 'TYPECAST_API_KEY', 'https://api.typecast.ai/v3/voices', lambda k: {'X-API-KEY': k}),
        ('KIE AI', 'KIE_API_KEY', 'https://api.kie.ai/api/v1/chat/credit', lambda k: {'Authorization': 'Bearer ' + k}),
    ]
    results = []
    for name, variable, url, header in specs:
        key = values.get(variable)
        result = check(name, key, url, header)
        if args.apply and result['authenticated']:
            set_key(str(ROOT / '.env'), variable, key.strip())
            result['saved_to_project'] = True
        results.append(result)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': 'local project API credentials', 'results': results}
    (ROOT / 'data').mkdir(exist_ok=True)
    (ROOT / 'data/media-connection-status.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if all(r['authenticated'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
