'use strict';
// WebGL renderer for the event viewport. workbench.js keeps the camera model,
// picking and all text; this module only moves geometry to the GPU so detector
// outlines (~400k segments) and animated tracks redraw at interactive rates.
// Returns null when WebGL is unavailable; the caller keeps its Canvas2D path.
window.HEPLabGL = (() => {
  const CUT = `
    uniform vec3 u_cut;
    varying vec2 v_world;
    bool removed(){
      return u_cut.z <= 1.0 && length(v_world)>0.000001 && dot(normalize(v_world),u_cut.xy)>u_cut.z;
    }`;
  const LINE_VS = `
    attribute vec3 a_position;
    uniform mat4 u_view;
    uniform float u_depth_scale;
    varying vec2 v_world;
    varying float v_depth;
    void main(){
      vec4 p = u_view * vec4(a_position, 1.0);
      v_depth = p.z;
      v_world = a_position.xy;
      gl_Position = vec4(p.xy, clamp(p.z*u_depth_scale,-0.99,0.99), 1.0);
    }`;
  const LINE_FS = `
    precision mediump float;
    ${CUT}
    uniform vec4 u_color;
    uniform float u_fog;
    varying float v_depth;
    void main(){
      if(removed()) discard;
      float fade = 1.0 - u_fog * smoothstep(-1.0, 1.0, v_depth);
      gl_FragColor = vec4(u_color.rgb, u_color.a * fade);
    }`;
  const SURFACE_VS = `
    attribute vec3 a_position;
    attribute vec3 a_normal;
    uniform mat4 u_view;
    uniform float u_depth_scale;
    varying vec2 v_world;
    varying float v_light;
    void main(){
      vec4 p=u_view*vec4(a_position,1.0);
      v_world=a_position.xy;
      v_light=0.34+0.66*abs(dot(normalize(a_normal),normalize(vec3(0.3,-0.5,0.8))));
      gl_Position=vec4(p.xy,clamp(p.z*u_depth_scale,-0.99,0.99),1.0);
    }`;
  const SURFACE_FS = `
    precision mediump float;
    ${CUT}
    uniform vec4 u_color;
    varying float v_light;
    void main(){
      if(removed())discard;
      gl_FragColor=vec4(u_color.rgb*v_light,u_color.a);
    }`;
  // Weighted blended transparency: accumulation and revealage in separate passes.
  // This keeps nested detector layers visible without camera-dependent face sorting.
  const ACCUM_FS = `
    precision mediump float;
    ${CUT}
    uniform vec4 u_color;
    varying float v_light;
    void main(){
      if(removed())discard;
      float weight=max(0.01,u_color.a);
      gl_FragColor=vec4(u_color.rgb*v_light*u_color.a*weight,u_color.a*weight);
    }`;
  const REVEAL_FS = `
    precision mediump float;
    ${CUT}
    uniform vec4 u_color;
    void main(){if(removed())discard;gl_FragColor=vec4(0.0,0.0,0.0,u_color.a);}`;
  const COMPOSITE_VS = `
    attribute vec2 a_position;
    varying vec2 v_uv;
    void main(){v_uv=a_position*0.5+0.5;gl_Position=vec4(a_position,0.0,1.0);}`;
  const COMPOSITE_FS = `
    precision mediump float;
    uniform sampler2D u_scene;
    uniform sampler2D u_accum;
    uniform sampler2D u_reveal;
    varying vec2 v_uv;
    void main(){
      vec3 scene=texture2D(u_scene,v_uv).rgb;
      vec4 accum=texture2D(u_accum,v_uv);
      float reveal=texture2D(u_reveal,v_uv).r;
      vec3 color=accum.rgb/max(accum.a,0.00001);
      gl_FragColor=vec4(color*(1.0-reveal)+scene*reveal,1.0);
    }`;
  // Screen-space ribbons: WebGL ignores lineWidth > 1 on most platforms.
  const TRACK_VS = `
    attribute vec3 a_a;
    attribute vec3 a_b;
    attribute vec3 a_info; // x: 0/1 endpoint, y: side, z: path length (m)
    uniform mat4 u_view;
    uniform vec2 u_resolution;
    uniform float u_width;
    varying float v_s;
    varying float v_side;
    void main(){
      vec4 a = u_view * vec4(a_a, 1.0), b = u_view * vec4(a_b, 1.0);
      vec2 delta = (b.xy - a.xy) * u_resolution;
      vec2 dir = length(delta) > 1e-6 ? normalize(delta) : vec2(1.0, 0.0);
      vec2 normal = vec2(-dir.y, dir.x);
      vec4 p = mix(a, b, a_info.x);
      gl_Position = vec4(p.xy + normal * a_info.y * u_width / u_resolution, 0.0, 1.0);
      v_s = a_info.z;
      v_side = a_info.y;
    }`;
  const TRACK_FS = `
    precision mediump float;
    uniform vec4 u_color;
    uniform float u_time;
    uniform float u_soft;
    varying float v_s;
    varying float v_side;
    void main(){
      if (v_s > u_time) discard;
      float edge = 1.0 - smoothstep(1.0 - u_soft, 1.0, abs(v_side));
      float head = 1.0 + 1.6 * (1.0 - smoothstep(0.0, 0.6, u_time - v_s));
      gl_FragColor = vec4(min(u_color.rgb * head, vec3(1.0)), u_color.a * edge);
    }`;
  const POINT_VS = `
    attribute vec3 a_position;
    attribute vec4 a_color;
    attribute vec2 a_info; // x: appears at path (m), y: size (px)
    uniform mat4 u_view;
    uniform float u_time;
    uniform float u_scale;
    varying vec4 v_color;
    void main(){
      vec4 p = u_view * vec4(a_position, 1.0);
      float age = u_time - a_info.x;
      float flash = age >= 0.0 ? 1.0 + 1.8 * (1.0 - smoothstep(0.0, 0.8, age)) : 0.0;
      gl_Position = vec4(p.xy, 0.0, 1.0);
      gl_PointSize = a_info.y * flash * u_scale;
      v_color = vec4(a_color.rgb, a_color.a * min(flash, 1.0));
    }`;
  const POINT_FS = `
    precision mediump float;
    varying vec4 v_color;
    void main(){
      float d = length(gl_PointCoord - 0.5);
      if (d > 0.5 || v_color.a <= 0.0) discard;
      gl_FragColor = vec4(v_color.rgb, v_color.a * (1.0 - smoothstep(0.15, 0.5, d)));
    }`;

  function compile(gl, vs, fs) {
    const program = gl.createProgram();
    for (const [type, source] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader));
      gl.attachShader(program, shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    const locations = {};
    const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < count; i++) { const name = gl.getActiveUniform(program, i).name; locations[name] = gl.getUniformLocation(program, name); }
    const attributes = {};
    const attributeCount = gl.getProgramParameter(program, gl.ACTIVE_ATTRIBUTES);
    for (let i = 0; i < attributeCount; i++) { const name = gl.getActiveAttrib(program, i).name; attributes[name] = gl.getAttribLocation(program, name); }
    return {program, uniforms: locations, attributes};
  }
  const hex = (value, alpha = 1) => {
    const n = parseInt(value.slice(1), 16);
    return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255, alpha];
  };

  function create(canvas) {
    let gl;
    try { gl = canvas.getContext('webgl', {antialias: true, alpha: false, premultipliedAlpha: false}); } catch { gl = null; }
    if (!gl) return null;
    let line, surface, accumulation, revealage, composite, track, point;
    try { line = compile(gl, LINE_VS, LINE_FS); surface=compile(gl,SURFACE_VS,SURFACE_FS); accumulation=compile(gl,SURFACE_VS,ACCUM_FS); revealage=compile(gl,SURFACE_VS,REVEAL_FS); composite=compile(gl,COMPOSITE_VS,COMPOSITE_FS); track = compile(gl, TRACK_VS, TRACK_FS); point = compile(gl, POINT_VS, POINT_FS); }
    catch (error) { console.warn('WebGL event display disabled:', error.message); return null; }
    const layers = new Map(); // key -> {buffer, count}
    let tracks = [], points = null, lost = false;
    let targets=null,transparencyUnavailable=false;
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); lost = true; });

    function upload(data) {
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      return buffer;
    }
    const quad=upload(new Float32Array([-1,-1,3,-1,-1,3]));
    const isSurface=layer=>layer.mode==='surface'||layer.mode==='shell';
    function freeTargets(value){
      if(!value)return;
      for(const item of value.items){gl.deleteFramebuffer(item.fbo);gl.deleteTexture(item.texture);}
      gl.deleteRenderbuffer(value.depth);
    }
    function makeTargets(w,h){
      const half=gl.getExtension('OES_texture_half_float');
      const halfColor=gl.getExtension('EXT_color_buffer_half_float');
      const float=gl.getExtension('OES_texture_float');
      const floatColor=gl.getExtension('WEBGL_color_buffer_float');
      const type=half&&halfColor?half.HALF_FLOAT_OES:float&&floatColor?gl.FLOAT:null;
      if(!type)return null;
      const value={width:w,height:h,depth:gl.createRenderbuffer(),items:[]};
      gl.bindRenderbuffer(gl.RENDERBUFFER,value.depth);
      gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,w,h);
      for(const format of [gl.UNSIGNED_BYTE,type,gl.UNSIGNED_BYTE]){
        const texture=gl.createTexture(),fbo=gl.createFramebuffer();
        value.items.push({texture,fbo});
        gl.bindTexture(gl.TEXTURE_2D,texture);
        gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
        gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,w,h,0,gl.RGBA,format,null);
        gl.bindFramebuffer(gl.FRAMEBUFFER,fbo);
        gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,texture,0);
        gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,value.depth);
        if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE){freeTargets(value);gl.bindFramebuffer(gl.FRAMEBUFFER,null);return null;}
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER,null);
      return value;
    }
    // mode 'lines': xyz segment pairs; 'triangles': xyz triangle corners (solid fills).
    function setLayer(key, segments, mode = 'lines') {
      if (layers.has(key)) gl.deleteBuffer(layers.get(key).buffer);
      if (!segments || !segments.length) { layers.delete(key); return; }
      let data = segments instanceof Float32Array ? segments : new Float32Array(segments);
      const count=data.length/3;
      if(mode==='surface'||mode==='shell'){
        const lit=new Float32Array(data.length*2);
        for(let i=0;i<data.length;i+=9){
          const n=window.HEPLabCutaway.normal(data.slice(i,i+3),data.slice(i+3,i+6),data.slice(i+6,i+9));
          for(let j=0;j<9;j+=3){
            const p=data.slice(i+j,i+j+3),r=Math.hypot(p[0],p[1])||1;
            lit.set([...p,...(mode==='shell'?[p[0]/r,p[1]/r,0]:n)],(i+j)*2);
          }
        }
        data=lit;
      }
      layers.set(key, {buffer: upload(data), count, mode});
    }
    // Each track: {id, points:[[x,y,z]...], color:'#rrggbb'}; returns cumulative path per point.
    function setTracks(list) {
      for (const item of tracks) gl.deleteBuffer(item.buffer);
      tracks = list.map(item => {
        const pts = item.points, data = new Float32Array(Math.max(0, pts.length - 1) * 6 * 9);
        const candidate = item.path_m;
        const validPath = Array.isArray(candidate) && candidate.length === pts.length && candidate.every((value, index) => Number.isFinite(value) && value >= 0 && (index === 0 || value >= candidate[index - 1]));
        const path = validPath ? candidate : [0];
        if (!validPath) for (let i = 1; i < pts.length; i++) path.push(path[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1], pts[i][2] - pts[i - 1][2]));
        let o = 0;
        for (let i = 0; i + 1 < pts.length; i++) {
          const a = pts[i], b = pts[i + 1];
          for (const [t, side] of [[0, -1], [0, 1], [1, 1], [0, -1], [1, 1], [1, -1]]) {
            data.set([a[0], a[1], a[2], b[0], b[1], b[2], t, side, t ? path[i + 1] : path[i]], o); o += 9;
          }
        }
        return {id: item.id, color: item.color, buffer: upload(data), count: data.length / 9, path, points: pts};
      });
      return tracks.map(t => t.path);
    }
    // Markers: {position:[x,y,z], color:'#rrggbb', alpha, at: path (m) when it appears, size: px}
    function setMarkers(list) {
      if (points) gl.deleteBuffer(points.buffer);
      if (!list.length) { points = null; return; }
      const data = new Float32Array(list.length * 9);
      list.forEach((m, i) => data.set([...m.position, ...hex(m.color, m.alpha ?? 1), m.at ?? 0, m.size ?? 6], i * 9));
      points = {buffer: upload(data), count: list.length};
    }
    function bindAttribute(program, name, size, stride, offset) {
      const location = program.attributes[name];
      if (location === undefined || location < 0) return;
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, stride * 4, offset * 4);
    }
    function resetAttributes() { const n = gl.getParameter(gl.MAX_VERTEX_ATTRIBS); for (let i = 0; i < n; i++) gl.disableVertexAttribArray(i); }

    // frame: {width, height, dpr, view (Float32Array 16, column-major), background,
    //   layers:[{key, color, alpha}], fog, time (m), selected, scale}
    function render(frame) {
      if (lost || gl.isContextLost()) return false;
      const w = Math.round(frame.width * frame.dpr), h = Math.round(frame.height * frame.dpr);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      gl.viewport(0, 0, w, h);
      const bg = hex(frame.background);
      const transparent=frame.layers.filter(spec=>{const layer=layers.get(spec.key);return layer&&isSurface(layer)&&spec.alpha>0&&spec.alpha<.999;});
      if(transparent.length){
        if(targets&&(targets.width!==w||targets.height!==h)){freeTargets(targets);targets=null;}
        if(!targets&&!transparencyUnavailable)targets=makeTargets(w,h);
        if(!targets){transparencyUnavailable=true;return false;}
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER,transparent.length?targets.items[0].fbo:null);
      gl.depthMask(true);gl.clearColor(bg[0], bg[1], bg[2], 1); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
      resetAttributes();
      function drawLayer(spec,pass='normal'){
        const layer = layers.get(spec.key);
        if (!layer||spec.alpha<=0)return;
        const solid=isSurface(layer),program=pass==='accum'?accumulation:pass==='reveal'?revealage:solid?surface:line;
        resetAttributes();gl.useProgram(program.program);
        gl.uniformMatrix4fv(program.uniforms.u_view,false,frame.view);
        gl.uniform1f(program.uniforms.u_depth_scale,frame.depthScale||.02);
        if(!solid)gl.uniform1f(line.uniforms.u_fog,frame.fog);
        const cut=spec.cutaway&&frame.cutaway?.enabled?frame.cutaway:null;
        const angle=(cut?.angle||0)*Math.PI/180;
        gl.uniform3f(program.uniforms.u_cut,Math.cos(angle),Math.sin(angle),cut?Math.cos(cut.opening*Math.PI/360):2);
        if(solid||spec.depthTest){gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);}else gl.disable(gl.DEPTH_TEST);
        gl.depthMask(solid&&pass==='normal');
        if(solid){gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,1);}else gl.disable(gl.POLYGON_OFFSET_FILL);
        gl.enable(gl.BLEND);
        if(pass==='accum')gl.blendFunc(gl.ONE,gl.ONE);
        else if(pass==='reveal')gl.blendFunc(gl.ZERO,gl.ONE_MINUS_SRC_ALPHA);
        else gl.blendFunc(gl.SRC_ALPHA, spec.additive === false ? gl.ONE_MINUS_SRC_ALPHA : gl.ONE);
        gl.bindBuffer(gl.ARRAY_BUFFER, layer.buffer);
        bindAttribute(program, 'a_position', 3, solid?6:3, 0);
        if(solid)bindAttribute(program,'a_normal',3,6,3);
        gl.uniform4fv(program.uniforms.u_color, hex(spec.color, spec.alpha));
        gl.drawArrays(solid||layer.mode === 'triangles' ? gl.TRIANGLES : gl.LINES, 0, layer.count);
      }
      if(transparent.length){
        const transparentSet=new Set(transparent);
        for(const spec of frame.layers)if(!transparentSet.has(spec)&&!spec.overlay)drawLayer(spec);
        gl.depthMask(false);
        gl.bindFramebuffer(gl.FRAMEBUFFER,targets.items[1].fbo);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
        for(const spec of transparent)drawLayer(spec,'accum');
        gl.bindFramebuffer(gl.FRAMEBUFFER,targets.items[2].fbo);gl.clearColor(1,1,1,1);gl.clear(gl.COLOR_BUFFER_BIT);
        for(const spec of transparent)drawLayer(spec,'reveal');
        gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.disable(gl.DEPTH_TEST);gl.disable(gl.BLEND);
        resetAttributes();gl.useProgram(composite.program);gl.bindBuffer(gl.ARRAY_BUFFER,quad);
        bindAttribute(composite,'a_position',2,2,0);
        ['u_scene','u_accum','u_reveal'].forEach((name,i)=>{gl.activeTexture(gl.TEXTURE0+i);gl.bindTexture(gl.TEXTURE_2D,targets.items[i].texture);gl.uniform1i(composite.uniforms[name],i);});
        gl.drawArrays(gl.TRIANGLES,0,3);gl.activeTexture(gl.TEXTURE0);
        for(const spec of frame.layers)if(spec.overlay)drawLayer(spec);
      }else for(const spec of frame.layers)drawLayer(spec);
      // Reconstructed objects and tracks are intentionally overlaid, never cut away.
      gl.disable(gl.DEPTH_TEST);gl.disable(gl.POLYGON_OFFSET_FILL);gl.depthMask(true);gl.enable(gl.BLEND);
      resetAttributes();
      gl.useProgram(track.program);
      gl.uniformMatrix4fv(track.uniforms.u_view, false, frame.view);
      gl.uniform2f(track.uniforms.u_resolution, w / 2, h / 2);
      gl.uniform1f(track.uniforms.u_time, frame.time);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
      for (const item of tracks) {
        const selected = item.id === frame.selected;
        gl.bindBuffer(gl.ARRAY_BUFFER, item.buffer);
        bindAttribute(track, 'a_a', 3, 9, 0); bindAttribute(track, 'a_b', 3, 9, 3); bindAttribute(track, 'a_info', 3, 9, 6);
        for (const [width, alpha, soft] of [[(selected ? 9 : 6) * frame.dpr, selected ? .32 : .2, 1], [(selected ? 2.4 : 1.5) * frame.dpr, 1, .5]]) {
          gl.uniform1f(track.uniforms.u_width, width);
          gl.uniform1f(track.uniforms.u_soft, soft);
          gl.uniform4fv(track.uniforms.u_color, hex(item.color, alpha));
          gl.drawArrays(gl.TRIANGLES, 0, item.count);
        }
      }
      if (points) {
        resetAttributes();
        gl.useProgram(point.program);
        gl.uniformMatrix4fv(point.uniforms.u_view, false, frame.view);
        gl.uniform1f(point.uniforms.u_time, frame.time);
        gl.uniform1f(point.uniforms.u_scale, frame.dpr);
        gl.bindBuffer(gl.ARRAY_BUFFER, points.buffer);
        bindAttribute(point, 'a_position', 3, 9, 0); bindAttribute(point, 'a_color', 4, 9, 3); bindAttribute(point, 'a_info', 2, 9, 7);
        gl.drawArrays(gl.POINTS, 0, points.count);
      }
      return true;
    }
    return {setLayer, setTracks, setMarkers, render, hasLayer: key => layers.has(key), get transparencyMode(){return targets?'weighted-blended':transparencyUnavailable?'canvas2d':'opaque';},get lost() { return lost || gl.isContextLost(); }};
  }
  return {create};
})();
