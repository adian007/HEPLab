"""Audit the shipped worker without changing production code or existing runs."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
BINARY = Path('D:/HEPLab/desktop/src-tauri/target/x86_64-pc-windows-msvc/release/heplab-worker.exe')
ROOT = HERE / 'frozen-worker-project'
ROOT.mkdir(parents=True, exist_ok=True)
p = subprocess.Popen([str(BINARY), '--project-root', str(ROOT)], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
hello = json.loads(p.stdout.readline())
identity = 0

def call(op, **args):
    global identity
    identity += 1
    p.stdin.write(json.dumps(dict(id=identity, op=op, args=args)) + '\n')
    p.stdin.flush()
    reply = json.loads(p.stdout.readline())
    if not reply['ok']:
        return {'ipc_error': reply['error']}
    return reply['result']

def run(**config):
    submitted = call('jobs.submit', config=config)
    if 'ipc_error' in submitted:
        return submitted
    for _ in range(600):
        job = call('jobs.get', job_id=submitted['id'])
        if job.get('status') not in ('queued', 'running'):
            return job
        time.sleep(.01)
    raise TimeoutError('job did not finish')

evidence = {'hello': hello, 'worker_sha256': hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            'session': call('workbench.session'), 'calibration': call('calibration.report'), 'cases': {}}
try:
    for name, config in [('default', {}), ('repeat', {}), ('zero_field', {'bz_tesla': 0.0}),
                         ('double_thickness', {'thickness_mm': 2.0}),
                         ('saturation', {'thickness_mm': 5.0}),
                         ('threshold_suppression', {'threshold_adc': 100.0}),
                         ('cms_tracker', {'field_model': 'cms_tracker'}),
                         ('dy_response', {'response_model': 'delphes_reference'}),
                         ('incompatible_response', {'response_model': 'delphes_reference', 'momentum_gev': 1.0})]:
        evidence['cases'][name] = run(**config)
    a = evidence['cases']['default']['result']
    b = evidence['cases']['repeat']['result']
    d = evidence['cases']['double_thickness']['result']
    response = evidence['cases']['dy_response']['result']
    evidence['checks'] = {
        'seed_reproducible': a == b,
        'deposit_doubles': all(abs(y['material']['deposit_gev'] / x['material']['deposit_gev'] - 2) < 1e-12 for x, y in zip(a['tracks'], d['tracks'])),
        'threshold_suppresses_all': all(not t['digit']['accepted'] for t in evidence['cases']['threshold_suppression']['result']['tracks']),
        'thick_slab_saturates_all': all(t['digit']['saturated'] for t in evidence['cases']['saturation']['result']['tracks']),
        'response_keeps_displayed_tracks_identical': all(x['points'] == y['points'] and x['digit'] == y['digit'] for x,y in zip(a['tracks'],response['tracks'])),
        'max_energy_residual_gev': max(abs(t['material']['energy_residual_gev']) for t in a['tracks']),
        'zero_field_max_xy_curvature_m': max(abs(point[1]) for point in evidence['cases']['zero_field']['result']['tracks'][0]['points'][:20]),
    }
    evidence['runs_list'] = call('runs.list')
finally:
    p.stdin.close()
    p.wait(timeout=30)
    evidence['exit_code'] = p.returncode
    evidence['stderr'] = p.stderr.read()
    (HERE / 'worker-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
print(json.dumps({'checks':evidence.get('checks'), 'case_status': {k: v.get('status',v.get('ipc_error')) for k,v in evidence['cases'].items()}, 'exit_code':p.returncode}, indent=2))
