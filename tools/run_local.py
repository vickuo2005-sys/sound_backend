"""Run the complete local API + dashboard against an isolated SQLite database."""
import argparse
import os
from pathlib import Path
import sys
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8786)
    parser.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1', 'localhost', '::1'])
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data_dir = (args.data_dir or root / '.local-runtime').resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)
    token_file = data_dir / 'upload-token.txt'
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32), encoding='utf-8')
    sys.path.insert(0, str(root))
    # This entry point is local-only: do not inherit a deployed database or bucket.
    for name in ('DATABASE_URL', 'GOOGLE_APPLICATION_CREDENTIALS', 'GCS_BUCKET_NAME',
                 'UPLOAD_TOKEN', 'DEVICE_TOKEN', 'DASHBOARD_ADMIN_TOKEN'):
        os.environ.pop(name, None)
    os.environ.update({
        'APP_ENV': 'development', 'DASHBOARD_V2_ENABLED': 'true',
        'DASHBOARD_SIMULATION_ENABLED': 'true', 'NODE_WEBSOCKET_ENABLED': 'true',
        'COMMAND_WEBSOCKET_ENABLED': 'true', 'COMMAND_REST_FALLBACK_ENABLED': 'true',
        'DASHBOARD_WRITE_TOKEN_REQUIRED': 'false',
        'UPLOAD_TOKEN': token_file.read_text(encoding='utf-8').strip(),
        'CLASSIFICATION_V1_ENABLED': 'true', 'CLASSIFICATION_V1_PERSISTENCE_ENABLED': 'true',
        'CLASSIFICATION_V1_WEBSOCKET_ENABLED': 'true',
    })
    import uvicorn
    uvicorn.run('main:app', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
