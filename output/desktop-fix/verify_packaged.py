"""Actual frozen-worker acceptance: native Rust, event storage, restart recovery."""
import json
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parent / 'packaged-project'
root.mkdir(exist_ok=True)
binary = Path('D:/HEPLab/desktop/src-tauri/binaries/heplab-worker-x86_64-pc-windows-msvc.exe')
env = {k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','HEPLAB_RUST'))}

def start():
    p = subprocess.Popen([str(binary),'--project-root',str(root)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=env)
    hello = json.loads(p.stdout.readline())
    assert hello['protocol']=='heplab-desktop-ipc-v1'
    return p

def call(p,op,**args):
    p.stdin.write(json.dumps(dict(id=1,op=op,args=args))+'\n');p.stdin.flush()
    reply=json.loads(p.stdout.readline());assert reply['ok'],reply
    return reply['result']

def close(p):
    p.stdin.close();p.wait(timeout=20);assert p.returncode==0,p.stderr.read()

p=start()
try:
    session=call(p,'workbench.session')
    assert session['engine']['rust_extension'],session
    submitted=call(p,'jobs.submit',config=dict(backend='rust',source_model='angular_sample',events=8,response_model='delphes_reference'))
    deadline=time.monotonic()+30
    while (job:=call(p,'jobs.get',job_id=submitted['id']))['status'] in ['queued','running']:
        assert time.monotonic()<deadline;time.sleep(.02)
    assert job['status']=='completed',job
    result=job['result'];assert result['backend']=='rust' and result['events']==8
    assert len(result['analysis']['samples'])==16
    event=call(p,'jobs.event',job_id=job['id'],index=3)
    assert event['event']==3 and event['tracks']!=result['tracks']
finally:
    close(p)
p=start()
try:
    restored=call(p,'jobs.get',job_id=job['id'])
    assert restored['result']==result
    assert call(p,'jobs.event',job_id=job['id'],index=3)==event
    runs=call(p,'runs.list');assert any(run['id']==job['id'] for run in runs)
finally:
    close(p)
report=dict(status='passed',runtime=session['engine'],run_id=job['id'],events=8,particles=16,
            stored_event_navigation=True,reopened_after_restart=True,
            max_energy_residual_gev=max(abs(s['energy_residual_gev']) for s in result['analysis']['samples']))
(root.parent/'packaged-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
