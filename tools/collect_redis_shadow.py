"""Read-only, exact-version staging collector. Does not generate test traffic."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import requests

BASE_URL = 'https://sound-backend-staging.onrender.com'
SERVICE_ID = 'srv-da6kdn61egvs7392r92g'


def validate(snapshot, expected_commit):
    build = snapshot.get('build', {})
    if build.get('render_git_commit') != expected_commit or build.get('render_service_id') != SERVICE_ID:
        raise ValueError('Unexpected staging build/service; collection stopped')
    # Fail closed rather than save a credential accidentally exposed by an API.
    text = json.dumps(snapshot)
    if any(scheme in text.lower() for scheme in ('rediss://', 'redis://', 'postgres://', 'postgresql://')):
        raise ValueError('Connection URL detected; snapshot not saved')
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--samples', type=int, default=120)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.samples <= 1800 or not 1 <= args.interval <= 60:
        parser.error('Use 1..1800 samples and 1..60 seconds interval')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwriting any previous evidence.
    with args.output.open('x', encoding='utf-8') as output:
        for index in range(args.samples):
            response = requests.get(BASE_URL+'/runtime-status', timeout=30)
            response.raise_for_status()
            snapshot = validate(response.json(), args.expected_commit)
            output.write(json.dumps({'collected_at': datetime.now(timezone.utc).isoformat(),
                'sequence': index, 'runtime_status': snapshot})+'\n')
            output.flush()
            if index+1 < args.samples:
                time.sleep(args.interval)
    print(json.dumps({'output': str(args.output), 'snapshots': args.samples,
                      'traffic_generated': False, 'android_test_claimed': False}))


if __name__ == '__main__':
    main()
