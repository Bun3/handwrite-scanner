"""Operator-only deployment. Credentials arrive via environment, never in artifacts."""
import json
import os
import sys
from pathlib import Path
import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKER = 'handwrite-error-reports'
BUCKET = 'handwrite-error-reports'


def main():
    account = os.environ.pop('CLOUDFLARE_ACCOUNT_ID')
    token = os.environ.pop('CLOUDFLARE_API_TOKEN')
    with httpx.Client(base_url=f'https://api.cloudflare.com/client/v4/accounts/{account}/',
                      headers={'Authorization': f'Bearer {token}'}, timeout=60) as client:
        def api(method, path, **kwargs):
            r = client.request(method, path, **kwargs)
            body = r.json()
            if not r.is_success or not body.get('success'):
                # Deliberately omit request headers, URLs containing account IDs and raw bodies.
                errors = [(e.get('code'), e.get('message')) for e in body.get('errors', [])]
                raise RuntimeError(f'{method} {path}: HTTP {r.status_code}, {errors}')
            return body.get('result')

        buckets = api('GET', 'r2/buckets')
        if not any(b['name'] == BUCKET for b in buckets.get('buckets', [])):
            api('POST', 'r2/buckets', json={'name': BUCKET, 'storageClass': 'Standard'})
        lifecycle = {'rules': [{'id': 'expire-diagnostics-30-days', 'enabled': True,
            'conditions': {'prefix': 'reports/'},
            'deleteObjectsTransition': {'condition': {'type': 'Age', 'maxAge': 30 * 86400}}}]}
        api('PUT', f'r2/buckets/{BUCKET}/lifecycle', json=lifecycle)
        api('PUT', f'r2/buckets/{BUCKET}/domains/managed', json={'enabled': False})
        domain = api('GET', 'workers/subdomain')['subdomain']
        scripts = api('GET', 'workers/scripts')
        exists = any(s['id'] == WORKER for s in scripts)
        metadata = {'main_module': 'worker.mjs', 'compatibility_date': '2026-09-18',
            'observability': {'enabled': False},
            'bindings': [
                {'type': 'r2_bucket', 'name': 'REPORTS', 'bucket_name': BUCKET},
                {'type': 'durable_object_namespace', 'name': 'QUOTA', 'class_name': 'ReportQuota'},
                {'type': 'ratelimit', 'name': 'IP_LIMIT', 'namespace_id': '2026091801',
                 'simple': {'limit': 5, 'period': 60}},
                {'type': 'plain_text', 'name': 'ACCEPT_REPORTS', 'text': 'true'}]}
        if not exists:
            metadata['migrations'] = {'new_tag': 'v1', 'steps': [{'new_sqlite_classes': ['ReportQuota']}]}
        api('PUT', f'workers/scripts/{WORKER}', files={
            'metadata': (None, json.dumps(metadata), 'application/json'),
            'worker.mjs': ('worker.mjs', (HERE / 'worker.mjs').read_bytes(), 'application/javascript+module')})
        api('POST', f'workers/scripts/{WORKER}/subdomain', json={'enabled': True, 'previews_enabled': False})
        saved_lifecycle = api('GET', f'r2/buckets/{BUCKET}/lifecycle')
        public = api('GET', f'r2/buckets/{BUCKET}/domains/managed')
        endpoint = f'https://{WORKER}.{domain}.workers.dev/reports'
        verification = {'endpoint': endpoint, 'lifecycle': saved_lifecycle,
                        'public_bucket_enabled': public.get('enabled')}
        output = ROOT / 'data' / 'cloudflare-setup' / 'deployment.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(verification, indent=2), encoding='utf-8')
        if public.get('enabled') is not False:
            raise RuntimeError('Bucket public access verification failed')
        print(json.dumps({'deployed': True, 'endpoint': endpoint, 'public_bucket_enabled': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
