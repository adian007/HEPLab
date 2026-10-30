"""Run real collisions through the shipped IPC worker without launcher variables."""
import json
import os
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
root=HERE/'Frozen Project';root.mkdir(exist_ok=True)
binary=Path('D:/HEPLab/desktop/src-tauri/binaries/heplab-worker-x86_64-pc-windows-msvc.exe')
env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','HEPLAB_SIM','HEPLAB_RUST'))}

def start():
    error_log=(HERE/'frozen-stderr.log').open('a',encoding='utf-8')
    p=subprocess.Popen([str(binary),'--project-root',str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error_log,text=True,encoding='utf-8',env=env)
    error_log.close()
    assert json.loads(p.stdout.readline())['protocol']=='heplab-desktop-ipc-v1'
    return p

def call(p,op,**args):
    p.stdin.write(json.dumps({'id':1,'op':op,'args':args})+'\n');p.stdin.flush()
    line=p.stdout.readline();assert line,(HERE/'frozen-stderr.log').read_text()
    reply=json.loads(line);assert reply['ok'],reply
    return reply['result']

def close(p):
    p.stdin.close();p.wait(timeout=30);assert p.returncode==0,(HERE/'frozen-stderr.log').read_text()

p=start()
try:
    session=call(p,'workbench.session');assert session['simulation']['available'],session
    print('Detected '+session['simulation']['host'],flush=True)
    submitted=call(p,'jobs.submit',config={'mode':'pythia','backend':'delphes','events':100,'seed':42})
    deadline=time.monotonic()+300
    while (job:=call(p,'jobs.get',job_id=submitted['id']))['status'] in ['queued','running']:
        assert time.monotonic()<deadline;time.sleep(.25)
    assert job['status']=='completed',job
    result=job['result'];assert result['summary']['events']==100
    assert result['analysis']['selected_events']>0
    selected=next(r['event'] for r in result['analysis']['event_rows'] if r['selected'])
    event=call(p,'jobs.event',job_id=job['id'],index=selected)
    assert event['event_info']['selected'] and len(event['tracks'])>=2
finally: close(p)
p=start()
try:
    assert call(p,'jobs.get',job_id=job['id'])['result']==result
    assert call(p,'jobs.event',job_id=job['id'],index=selected)==event
    started=time.time()
    stopped=call(p,'jobs.submit',config={'mode':'pythia','backend':'delphes','events':1000,'seed':43})
    deadline=time.monotonic()+60
    while not any(f.stat().st_mtime>=started for f in (root/'artifacts').glob('.sim-*/events.root')):
        state=call(p,'jobs.get',job_id=stopped['id'])
        assert state['status'] in ['queued','running'],state
        assert time.monotonic()<deadline
        time.sleep(.1)
    call(p,'jobs.cancel',job_id=stopped['id'])
    while (state:=call(p,'jobs.get',job_id=stopped['id']))['status'] in ['queued','running']:
        assert time.monotonic()<deadline
        time.sleep(.1)
    assert state['status']=='cancelled',state
    assert not (root/'artifacts'/(stopped['id']+'.json')).exists()
    assert not (root/'artifacts'/(stopped['id']+'-simulation')).exists()
finally: close(p)
report={'status':'passed','runtime':session['simulation'],'run_id':job['id'],
        'events':100,'selected_events':result['analysis']['selected_events'],
        'summary':result['summary'],'cutflow':result['analysis']['cutflow'],
        'selected_event_navigation':True,'restart_reopened':True,'active_generation_cancelled':True,
        'output_directory':result['output_directory']}
(HERE/'frozen-collision-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
