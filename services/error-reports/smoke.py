"""Synthetic-only public endpoint smoke test. Never collects local diagnostics."""
import json
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--feedback', action='store_true')
options = parser.parse_args()
endpoint = json.loads((ROOT / 'data/cloudflare-setup/deployment.json').read_text())['endpoint']
report = dict(schema=1, report_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat(),
              app_version='0.9.0', system=dict(os='Windows', release='synthetic', architecture='AMD64',
              cpu_threads=8, ram_gb=16, disk_free_gb=100, cpu='synthetic', os_build='synthetic'), model='synthetic', error_code='smoke_test',
              screen='unknown', jobs={}, job_progress=[{'state': 'error', 'phase': 'recognizing', 'page': 2, 'total_pages': 105}],
              events=[], contact='', description='Synthetic deployment verification; no user data.')
if options.feedback:
    report.update(kind='feedback', category='suggestion')
report['environment'] = {'python_version':'3.14.0', 'ram_available_gb':4, 'process_memory_mb':256,
                         'graphics':[{'name':'Synthetic GPU','driver_version':'1.0'}], 'engine_state':'idle'}
report['browser'] = {'user_agent':'Synthetic browser', 'language':'ko-KR', 'viewport_width':1280,
                     'viewport_height':720, 'pixel_ratio':1}
with httpx.Client(timeout=30) as client:
    health = client.get(endpoint.replace('/reports', '/health'))
    assert health.status_code == 200, health.status_code
    accepted = client.post(endpoint, json=report)
    assert accepted.status_code == 201, (accepted.status_code, accepted.text)
    assert accepted.json()['receipt'] == report['report_id']
    denied = client.get(endpoint + '/' + report['report_id'])
    assert denied.status_code == 404
    malformed = client.post(endpoint, json={**report, 'raw_log': 'DO NOT STORE'})
    assert malformed.status_code == 400
    oversized = client.post(endpoint, content=b'x' * (256*1024 + 1), headers={'content-type':'application/json'})
    assert oversized.status_code == 400
    # Malformed requests exercise the limiter without creating additional objects.
    statuses = [client.post(endpoint, json={}).status_code for _ in range(6)]
    assert 429 in statuses, statuses
result = {'receipt': report['report_id'], 'kind': report.get('kind', 'error'), 'accepted': True, 'public_read_denied': True,
          'invalid_rejected': True, 'oversized_rejected': True, 'rate_limited': True}
(ROOT / 'data/cloudflare-setup/smoke.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
