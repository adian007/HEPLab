'use strict';
// Shared CPU clipping for the Canvas2D renderer and independent regression tests.
// A sector around the beam (Z) axis is removed; event objects are never clipped.
(() => {
  const dot=(p,n)=>p[0]*n[0]+p[1]*n[1];
  const mix=(a,b,t)=>a.map((v,k)=>v+(b[k]-v)*t);
  function planes(cut){
    if(!cut?.enabled)return [];
    const half=cut.opening*Math.PI/360,a=cut.angle*Math.PI/180;
    return [[-Math.sin(a-half),Math.cos(a-half)],[Math.sin(a+half),-Math.cos(a+half)]];
  }
  function halfPolygon(poly,n,positive){
    const out=[];if(!poly.length)return out;
    let a=poly.at(-1),da=dot(a,n)*(positive?1:-1);
    for(const b of poly){
      const db=dot(b,n)*(positive?1:-1);
      if((da>=0)!==(db>=0))out.push(mix(a,b,da/(da-db)));
      if(db>=0)out.push(b);
      a=b;da=db;
    }
    return out;
  }
  function polygon(poly,cut){
    const ns=planes(cut);if(!ns.length)return [poly];
    return [halfPolygon(poly,ns[0],false),halfPolygon(halfPolygon(poly,ns[0],true),ns[1],false)].filter(p=>p.length>=3);
  }
  function segment(a,b,cut){
    const ns=planes(cut);if(!ns.length)return [[a,b]];
    let low=0,high=1;
    for(const n of ns){
      const d=dot(a,n),delta=dot(b,n)-d;
      if(Math.abs(delta)<1e-12){if(d<0)return [[a,b]];continue;}
      const t=-d/delta;
      if(delta>0)low=Math.max(low,t);else high=Math.min(high,t);
    }
    if(low>=high)return [[a,b]];
    const out=[];
    if(low>0)out.push([a,mix(a,b,Math.min(1,low))]);
    if(high<1)out.push([mix(a,b,Math.max(0,high)),b]);
    return out;
  }
  function normal(a,b,c){
    const u=b.map((v,k)=>v-a[k]),v=c.map((x,k)=>x-a[k]);
    const n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],length=Math.hypot(...n)||1;
    return n.map(x=>x/length);
  }
  const api={planes,polygon,segment,normal};
  if(typeof module!=='undefined')module.exports=api;
  else window.HEPLabCutaway=api;
})();
