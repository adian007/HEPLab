'use strict';
// Exercise the workbench's real geometry and rendering functions without a GPU.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const cutaway=require('../src/heplab/server/static/detector-cutaway.js');
const source=fs.readFileSync(path.join(__dirname,'../src/heplab/server/static/workbench.js'),'utf8');
const section=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end));

function harness(renderer=null){
  const elements=new Map(),strokes=[],fills=[],rectangles=[];
  const element=()=>({children:[],style:{},dataset:{},checked:false,value:'cms',append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},setAttribute(){}});
  const $=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  const context={scale(){},setTransform(){},clearRect(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},arc(){},fillRect(){},fillText(){},setLineDash(){},
    stroke(){strokes.push(this.strokeStyle);},fill(){fills.push(this.fillStyle);},strokeRect(){rectangles.push(true);}};
  const objects={jets:[{pt:30,eta:0,phi:0,em_fraction:.3,hadronic_fraction:.6}],
    electrons:[{index:0,pt:1,eta:0,phi:0,points:[[0,0,0],[.7,.9,0]]}],
    photons:[{pt:10,eta:0,phi:1}],taus:[{pt:10,eta:0,phi:2}],isotracks:[{pt:5,eta:0,phi:2}],met:{pt:20,phi:1}};
  const sandbox={$,document:{createElement:element},window:{devicePixelRatio:1,HEPLabCutaway:cutaway},context,
    canvas:{getBoundingClientRect:()=>({width:800,height:600})},renderer,
    result:{mode:'cms',objects,tracks:[{object_id:0,charge:-1,points:[[0,0,0],[2,0,0]],trajectory:{crossings:[{surface_id:'pixel',path_m:1,position_m:[1,0,0]}]}}]},
    projection:'xy',orbit:[0,0],roll:0,trackerShell:null,layerOpacity:new Map(),zoom:1,pan:[0,0],selected:null,screenTracks:[],detectorGeometry:null,
    displayLayers:new Map(),displaySurfaces:new Map(),displayRemainders:new Map(),DISPLAY_COLORS:{pixel:'#d68c9a',strips:'#75ad98'},hiddenDisplay:new Set(),hiddenSurfaces:new Set(),syncedEvent:null,syncedMarkers:'',
    trackPaths:[],playback:{time:Infinity,max:0},trackColor:()=> '#68b9ef'};
  vm.createContext(sandbox);
  vm.runInContext(section('function rotate(', 'const DISPLAY_COLORS=')+
    section('const OBJECT_GROUPS=', 'function drawTriadAndScale(')+
    section('function draw() {', 'function updateTimeline(){'),sandbox);
  return {sandbox,objects,$,strokes,fills,rectangles,run:code=>vm.runInContext(code,sandbox)};
}

test('hidden layers remain available across events and taus can be enabled',()=>{
  const h=harness();
  h.run('syncEventGeometry();renderObjectToggles();');
  const checkbox=label=>h.$('object-layers').children.find(row=>row.children[2].textContent===label)?.children[0];
  assert.equal(checkbox('Taus').checked,false);
  const jets=checkbox('Jets (anti-kT 0.4)');
  jets.checked=false;jets.onchange();
  h.run('result={...result};syncEventGeometry();renderObjectToggles();');
  const hidden=checkbox('Jets (anti-kT 0.4)');
  assert.equal(hidden.checked,false);
  hidden.checked=true;hidden.onchange();
  assert.equal(h.run("hiddenObjects.has('jets')"),false);
  const tau=checkbox('Taus');tau.checked=true;tau.onchange();
  assert.equal(h.run("hiddenObjects.has('taus')"),false);
  assert.ok(h.strokes.includes('#c78bff'));
});

test('electron tower front face is centered on the propagated track endpoint',()=>{
  const h=harness();
  const center=h.run(`(()=>{
    const data=objectGeometry(result.objects).layers.find(l=>l.key==='obj:electron-towers').data;
    return [0,1,2].map(k=>[0,3,6,9,12,15].reduce((sum,i)=>sum+data[i+k],0)/6);
  })()`);
  center.forEach((v,k)=>assert.ok(Math.abs(v-h.objects.electrons[0].points.at(-1)[k])<1e-12));
});

for(const lost of [false,true])test(`Canvas2D draws every reconstructed object group with ${lost?'lost':'no'} WebGL context`,()=>{
  const h=harness(lost?{lost:true}:null);
  h.run('draw();renderObjectToggles();');
  for(const color of ['#f2d14b','#5fe39a','#c9f27c','#9fb3c8','#ff4fd8'])assert.ok(h.strokes.includes(color),color);
  assert.ok(h.fills.includes('#ff5a4f'),'calorimeter towers');
  assert.ok(h.sandbox.playback.max>=2.5);
  assert.ok(h.$('object-layers').children.length>=6);
  h.strokes.length=0;
  h.run("hiddenObjects.add('photons');syncedEvent=null;draw();");
  assert.ok(!h.strokes.includes('#c9f27c'));
});

test('Canvas2D replay clips tracks and delays predicted crossings',()=>{
  const h=harness();
  h.run('playback.time=.5;draw();');
  assert.equal(h.rectangles.length,0);
  const points=h.run('visibleTrackPoints(result.tracks[0],playback.time)');
  assert.equal(points.at(-1)[0],.5);
  assert.ok(points.every(p=>p[0]<=.5));
  h.run('playback.time=Infinity;draw();');
  assert.equal(h.rectangles.length,1);
});

test('WebGL visibility filters preserve toggles and electron/MET tracks',()=>{
  let frame,tracks;
  const h=harness({lost:false,setLayer(){},setMarkers(){},setTracks(value){tracks=value;},render(value){frame=value;}});
  Object.assign(h.sandbox,{
    viewFrame:()=>({width:800,height:600,extent:14,scale:10,project:p=>p.slice(0,2)}),
    viewMatrix:()=>[],syncStaticLayers(){},drawTriadAndScale(){}
  });
  h.run("hiddenObjects.add('jets');hiddenObjects.add('electrons');draw();renderObjectToggles();");
  assert.ok(!frame.layers.some(layer=>layer.key==='obj:jets'));
  assert.ok(!tracks.some(track=>track.id==='e0'));
  assert.ok(tracks.some(track=>track.id==='met'));
  assert.ok(h.$('object-layers').children.some(row=>row.children[2].textContent==='Jets (anti-kT 0.4)'));
  h.run("hiddenObjects.delete('electrons');syncedEvent=null;draw();");
  assert.ok(tracks.some(track=>track.id==='e0'));
});

test('replay starts on the Canvas2D path',()=>{
  const h=harness();
  let frames=0;
  Object.assign(h.sandbox,{reducedMotion:false,performance:{now:()=>0},
    updateTimeline(){},cancelAnimationFrame(){},requestAnimationFrame(){frames++;return frames;},tick(){}});
  h.run(section('function replay(fromStart=', 'function pauseReplay('));
  h.run('draw();replay();');
  assert.equal(h.sandbox.playback.playing,true);
  assert.equal(h.sandbox.playback.time,0);
  assert.equal(frames,1);
});

function cameraHarness(){
  const h=harness(),handlers={};
  h.sandbox.canvas.parentElement={addEventListener(name,fn){handlers[name]=fn;}};
  h.sandbox.canvas.getBoundingClientRect=()=>({left:10,top:20,width:800,height:600});
  h.sandbox.document.querySelectorAll=()=>[];
  h.run(section('function updateZoomControls(){', "canvas.addEventListener('pointerdown'"));
  return {...h,handlers};
}

test('zoom preserves the world point under the cursor and supports core magnification',()=>{
  const h=cameraHarness();
  h.run('pan=[30,-20];zoom=2;');
  const before=h.run('[(600-400-pan[0])/zoom,(200-300-pan[1])/zoom]');
  h.run('changeZoom(1.4,[600,200]);');
  const after=h.run('[(600-400-pan[0])/zoom,(200-300-pan[1])/zoom]');
  after.forEach((v,k)=>assert.ok(Math.abs(v-before[k])<1e-10));
  h.run('changeZoom(1e6);');
  assert.equal(h.sandbox.zoom,128);
  assert.equal(h.$('zoom-in').disabled,true);
  h.run('changeZoom(1e-6);');
  assert.equal(h.sandbox.zoom,.1);
  assert.equal(h.$('zoom-out').disabled,true);
});

test('core preset restores pixel modules even when outlines were hidden',()=>{
  const h=cameraHarness();
  h.run("hiddenDisplay.add('pixel');pan=[300,200];zoom=8;");
  h.$('focus-core').onclick();
  assert.equal(h.$('detector-focus').value,'pixel');
  assert.equal(h.$('show-modules').checked,true);
  assert.equal(h.$('show-grid').checked,false);
  assert.equal(h.run("hiddenDisplay.has('pixel')"),false);
  assert.equal(h.sandbox.zoom,1);
  assert.ok(h.sandbox.pan.every(v=>v===0));
});

test('wheel handles line deltas but leaves live panel scrolling alone',()=>{
  const h=cameraHarness();let prevented=0;
  const event={deltaY:-3,deltaMode:1,clientX:410,clientY:320,target:{closest:()=>null},preventDefault(){prevented++;}};
  h.handlers.wheel(event);
  assert.ok(Math.abs(h.sandbox.zoom-Math.exp(.096))<1e-10);
  assert.equal(prevented,1);
  h.handlers.wheel({...event,target:{closest:()=>({})}});
  assert.equal(prevented,1);
});

test('scale bars stay readable from the full detector to millimetre details',()=>{
  const h=harness();
  for(const scale of [1,20,500,10000,100000]){
    const bar=h.run(`scaleBar(${scale})`);
    assert.ok(bar.length*scale>10 && bar.length*scale<=90);
    assert.match(bar.label,/ (m|cm|mm)$/);
  }
});

test('cutaway removes only the selected beam-axis sector and clips crossing edges',()=>{
  const cut={enabled:true,angle:0,opening:90};
  assert.equal(cutaway.segment([1,0,0],[2,0,1],cut).length,0);
  assert.equal(cutaway.segment([-1,0,0],[-2,0,1],cut).length,1);
  const edge=cutaway.segment([-2,1,0],[2,1,4],cut);
  assert.equal(edge.length,1);
  assert.ok(Math.abs(edge[0][1][0]-1)<1e-10);
  assert.ok(Math.abs(edge[0][1][2]-3)<1e-10);
  assert.equal(cutaway.segment([1,0,0],[2,0,1],{...cut,enabled:false}).length,1);
});

test('CPU cutaway polygon pieces preserve the visible area without filling the opening',()=>{
  const poly=[[-2,-2,0],[2,-2,0],[2,2,0],[-2,2,0]];
  const pieces=cutaway.polygon(poly,{enabled:true,angle:0,opening:90});
  const area=p=>Math.abs(p.reduce((n,a,i)=>{const b=p[(i+1)%p.length];return n+a[0]*b[1]-b[0]*a[1];},0))/2;
  assert.ok(Math.abs(pieces.reduce((n,p)=>n+area(p),0)-12)<1e-10);
  for(const p of pieces)for(const point of p)assert.ok(point[0]<=Math.abs(point[1])+1e-9);
});

test('solid detector uses surface buffers and clipping; event layers remain uncut',()=>{
  let frame;
  const h=harness({lost:false,setLayer(){},setMarkers(){},setTracks(){},render(value){frame=value;}});
  Object.assign(h.sandbox,{viewFrame:()=>({width:800,height:600,extent:14,scale:10,project:p=>p.slice(0,2)}),viewMatrix:()=>[],syncStaticLayers(){},drawTriadAndScale(){}});
  h.sandbox.displayLayers.set('pixel',new Float32Array([0,0,0,1,0,0]));
  h.sandbox.displaySurfaces.set('pixel',new Float32Array([0,0,0,1,0,0,0,1,0]));
  h.$('detector-style').value='solid';h.$('show-modules').checked=true;h.$('cutaway').checked=true;
  h.$('cutaway-angle').value='315';h.$('cutaway-opening').value='100';
  h.run('draw();');
  assert.ok(frame.layers.some(l=>l.key==='solid:pixel'&&l.cutaway));
  assert.ok(frame.layers.filter(l=>l.key.startsWith('obj:')).every(l=>!l.cutaway));
  assert.equal(frame.cutaway.angle,315);
});

test('orthographic solid views retain depth for occlusion without changing their projection',()=>{
  const h=harness();
  h.run(section('function viewMatrix(', 'function polylineSegments('));
  const xy=h.run("projection='xy';viewMatrix({width:800,height:600,extent:14,scale:10,origin:[400,300]})");
  assert.ok(xy[10]>0);assert.equal(xy[2],0);assert.equal(xy[6],0);
  const xz=h.run("projection='xz';viewMatrix({width:800,height:600,extent:14,scale:10,origin:[400,300]})");
  assert.ok(xz[6]<0);assert.ok(xz[9]>0);assert.equal(xz[10],0);
});

test('layer opacity applies only to detector geometry and CPU alpha is restored',()=>{
  let frame;
  const h=harness({lost:false,setLayer(){},setMarkers(){},setTracks(){return [];},render(value){frame=value;}});
  Object.assign(h.sandbox,{viewFrame:()=>({width:800,height:600,extent:14,scale:10,origin:[400,300],project:p=>p}),viewMatrix:()=>new Float32Array(16),syncStaticLayers(){},drawTriadAndScale(){},DISPLAY_ALPHA:{pixel:.35},SURFACE_COLORS:{}});
  h.$('detector-style').value='solid';h.$('show-modules').checked=true;
  h.sandbox.displaySurfaces.set('pixel',new Float32Array([0,0,0,1,0,0,0,1,0]));
  h.sandbox.displayLayers.set('pixel',new Float32Array([0,0,0,1,0,0]));
  h.sandbox.layerOpacity.set('pixel',.25);h.run('draw()');
  assert.equal(frame.layers.find(l=>l.key==='solid:pixel').alpha,.25);
  assert.equal(frame.layers.find(l=>l.key==='cms:pixel').alpha,.55*.25);
  assert.ok(frame.layers.filter(l=>l.key.startsWith('obj:')).every(l=>l.overlay===true));
  h.sandbox.layerOpacity.set('pixel',0);h.run('draw()');
  assert.equal(frame.layers.find(l=>l.key==='solid:pixel').alpha,0);
  h.sandbox.renderer=null;h.run('draw()');
  assert.equal(h.sandbox.context.globalAlpha,1);
  assert.ok(h.strokes.includes('#68b9ef'));
});

test('opacity values are clamped, persisted and reject non-finite input',()=>{
  const h=harness();let saved;
  h.sandbox.localStorage={setItem(key,value){saved=JSON.parse(value);}};
  h.sandbox.document.querySelectorAll=()=>[];
  h.run("setOpacity('pixel',2);setOpacity('strips',-1);setOpacity('shell',.2);setOpacity('pixel',NaN);setOpacity('bad',.5)");
  assert.deepEqual(saved,{pixel:1,strips:0,shell:.2});
  assert.equal(h.sandbox.layerOpacity.has('bad'),false);
});

test('tracker shell uses the loaded envelope dimensions without altering geometry',()=>{
  const h=harness();
  h.sandbox.detectorGeometry={surfaces:[{subsystem:'tracker-envelope',kind:'cylinder',radius_m:1.1,half_length_m:2.8}]};
  const before=JSON.stringify(h.sandbox.detectorGeometry),data=h.run('shellGeometry()');
  assert.equal(data.length,96*18);
  for(let i=0;i<data.length;i+=3){assert.ok(Math.abs(Math.hypot(data[i],data[i+1])-1.1)<1e-6);assert.ok(Math.abs(Math.abs(data[i+2])-2.8)<1e-6);}
  assert.equal(JSON.stringify(h.sandbox.detectorGeometry),before);
  assert.equal(h.run('shellGeometry()'),data);
});

test('camera roll agrees between CPU projection and the GPU matrix',()=>{
  const h=harness();h.run(section('function viewMatrix(', 'function polylineSegments('));
  h.sandbox.projection='3d';h.sandbox.orbit=[-.65,.25];h.sandbox.roll=Math.PI/2;
  const point=[.3,.7,1.1],cpu=h.run('rotate([.3,.7,1.1])'),m=h.run('viewMatrix({width:800,height:600,extent:3,scale:100,origin:[400,300]})');
  const gpu=[0,1].map(k=>m[k]*point[0]+m[k+4]*point[1]+m[k+8]*point[2]+m[k+12]);
  assert.ok(Math.abs(gpu[0]*400/100-cpu[0])<1e-6);
  assert.ok(Math.abs(gpu[1]*300/100-cpu[1])<1e-6);
});
