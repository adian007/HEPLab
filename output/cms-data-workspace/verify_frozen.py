import csv, io, json, os, subprocess, time
from pathlib import Path

base=Path('D:/HEPLab/output/cms-data-workspace')
root=base/'Frozen Project';root.mkdir(exist_ok=True)
env={k:v for k,v in os.environ.items() if not k.startswith(('HEPLAB','PYTHON'))}
binary=Path('D:/HEPLab/desktop/src-tauri/binaries/heplab-worker-x86_64-pc-windows-msvc.exe')
with (base/'frozen-stderr.log').open('w') as log:
    p=subprocess.Popen([str(binary),'--project-root',str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',env=env)
    hello=json.loads(p.stdout.readline()); assert 'data.analyze' in hello['operations']
    sequence=0
    def call(op,**args):
        global sequence
        sequence+=1;p.stdin.write(json.dumps(dict(id=sequence,op=op,args=args))+'\n');p.stdin.flush()
        response=json.loads(p.stdout.readline());assert response['id']==sequence and response['ok'],response
        return response['result']
    start=time.monotonic()
    library=call('data.library');assert len(library)==2
    loaded=[call('data.load',dataset_id=x['id']) for x in library];assert all(x['events']==100000 for x in loaded)
    default=call('data.analyze',config={})
    assert [x['selected_events'] for x in default['populations'].values()]==[10863,11430]
    tight=call('data.analyze',config=dict(min_pt=30.,leading_pt=40.))
    assert [x['selected_events'] for x in tight['populations'].values()]==[6678,6981] and tight['root_reads']==2
    count=0;offset=0
    while True:
        page=call('data.rows',analysis_id=default['id'],role='data',offset=offset)
        rows=list(csv.reader(io.StringIO(page['text'])));count+=len(rows)-(offset==0)
        if page['next_offset']>=page['total']:break
        offset=page['next_offset']
    assert count==10863
    assert call('data.get',analysis_id=default['id'])['config']==default['config']
    output=dict(status='passed',library=[x['name'] for x in library],baseline={k:v['selected_events'] for k,v in default['populations'].items()},tight={k:v['selected_events'] for k,v in tight['populations'].items()},root_reads=tight['root_reads'],exported_data_rows=count,elapsed_seconds=round(time.monotonic()-start,2),analysis_id=default['id'])
    (base/'frozen-acceptance.json').write_text(json.dumps(output,indent=2));print(json.dumps(output))
    p.stdin.close();p.wait(timeout=15);assert p.returncode==0
