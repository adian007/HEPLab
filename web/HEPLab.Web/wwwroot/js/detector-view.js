'use strict';

// Small, dependency-free perspective renderer for the fixed, versioned teaching fixture.
// It draws only fixture coordinates and declared envelope geometry; it runs no physics.
(() => {
  const host = document.querySelector('[data-detector-view]');
  if (!host) return;
  const canvas = host.querySelector('canvas');
  const context = canvas.getContext('2d');
  const status = host.querySelector('[data-view-status]');
  const label = host.querySelector('[data-camera-label]');
  const fixtureUrl = host.dataset.fixtureUrl;
  if (!context) {
    setStatus('This browser does not provide the 2D canvas needed for the detector view. The synthetic event record remains available below.', 'error');
    return;
  }
  const presets = {
    perspective: { azimuth: 0.82, elevation: 0.48, distance: 17, label: '3D perspective' },
    transverse: { azimuth: 0, elevation: 1.48, distance: 17, label: 'Transverse x–y' },
    longitudinal: { azimuth: Math.PI / 2, elevation: 0.03, distance: 17, label: 'Longitudinal x–z' },
  };
  let camera = { ...presets.perspective };
  let scene = null;
  let cssWidth = 0;
  let cssHeight = 0;
  let pointer = null;
  let colors = {};

  function setStatus(message, state) {
    status.textContent = message;
    status.dataset.state = state;
  }

  function resize() {
    const box = canvas.getBoundingClientRect();
    if (!box.width || !box.height) return;
    cssWidth = box.width;
    cssHeight = box.height;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(cssWidth * ratio);
    canvas.height = Math.round(cssHeight * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    render();
  }

  function project(point) {
    const az = camera.azimuth;
    const el = camera.elevation;
    const forward = [Math.cos(el) * Math.cos(az), Math.cos(el) * Math.sin(az), Math.sin(el)];
    const right = [-Math.sin(az), Math.cos(az), 0];
    const up = [-Math.sin(el) * Math.cos(az), -Math.sin(el) * Math.sin(az), Math.cos(el)];
    const depth = camera.distance - (point[0] * forward[0] + point[1] * forward[1] + point[2] * forward[2]);
    const focal = Math.min(cssWidth, cssHeight) * 1.02;
    const scale = focal / Math.max(depth, 1);
    return {
      x: cssWidth * 0.5 + (point[0] * right[0] + point[1] * right[1] + point[2] * right[2]) * scale,
      y: cssHeight * 0.51 - (point[0] * up[0] + point[1] * up[1] + point[2] * up[2]) * scale,
      scale,
    };
  }

  function line(points, color, width = 1, dash = [], alpha = 1) {
    if (points.length < 2) return;
    context.beginPath();
    const first = project(points[0]);
    context.moveTo(first.x, first.y);
    for (let i = 1; i < points.length; i++) {
      const p = project(points[i]);
      context.lineTo(p.x, p.y);
    }
    context.strokeStyle = color;
    context.lineWidth = width;
    context.globalAlpha = alpha;
    context.setLineDash(dash);
    context.stroke();
    context.setLineDash([]);
    context.globalAlpha = 1;
  }

  function circleAt(radius, z, color, alpha, innerRadius = 0) {
    const count = 64;
    if (!innerRadius) {
      const points = Array.from({ length: count + 1 }, (_, i) => {
        const angle = i / count * Math.PI * 2;
        return [radius * Math.cos(angle), radius * Math.sin(angle), z];
      });
      line(points, color, 0.85, [], alpha);
      return;
    }
    for (const r of [radius, innerRadius]) {
      const points = Array.from({ length: count + 1 }, (_, i) => {
        const angle = i / count * Math.PI * 2;
        return [r * Math.cos(angle), r * Math.sin(angle), z];
      });
      line(points, color, 0.8, [], alpha);
    }
    for (let i = 0; i < 8; i++) {
      const a = i / 8 * Math.PI * 2;
      line([[innerRadius * Math.cos(a), innerRadius * Math.sin(a), z], [radius * Math.cos(a), radius * Math.sin(a), z]], color, 0.65, [], alpha * 0.7);
    }
  }

  function cylinder(surface) {
    const color = surface.id === 'solenoid-bore' ? colors.blue : surface.id === 'strip-envelope' ? colors.accent : colors.subtle;
    const alpha = surface.id === 'solenoid-bore' ? 0.54 : surface.id === 'strip-envelope' ? 0.48 : 0.42;
    const z0 = -surface.half_length_m;
    const z1 = surface.half_length_m;
    for (const z of [z0, 0, z1]) circleAt(surface.radius_m, z, color, z === 0 ? alpha * 0.72 : alpha);
    for (let i = 0; i < 16; i++) {
      const a = i / 16 * Math.PI * 2;
      line([[surface.radius_m * Math.cos(a), surface.radius_m * Math.sin(a), z0], [surface.radius_m * Math.cos(a), surface.radius_m * Math.sin(a), z1]], color, 0.62, [], alpha * (i % 4 === 0 ? 0.82 : 0.42));
    }
  }

  function arrow(from, to, color, width = 1.5, headSize = 4) {
    line([from, to], color, width, [], 0.9);
    const a = project(from);
    const b = project(to);
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    context.beginPath();
    context.moveTo(b.x, b.y);
    context.lineTo(b.x - headSize * Math.cos(angle - 0.48), b.y - headSize * Math.sin(angle - 0.48));
    context.lineTo(b.x - headSize * Math.cos(angle + 0.48), b.y - headSize * Math.sin(angle + 0.48));
    context.closePath();
    context.fillStyle = color;
    context.fill();
  }

  function labelAt(text, point, color, offsetX = 5, offsetY = -5) {
    const p = project(point);
    context.fillStyle = color;
    context.font = '11px "Plex Mono", monospace';
    context.fillText(text, p.x + offsetX, p.y + offsetY);
  }

  function drawField() {
    const color = colors.blue;
    for (const [x, y] of [[0, 0], [-1.55, 0], [1.55, 0], [0, -1.55], [0, 1.55]]) {
      arrow([x, y, -0.32], [x, y, 0.32], color, 1.05, 3.5);
    }
    labelAt('Bz = +3.8 T', [0, 0, 0.48], color, 9, -7);
  }

  function drawAxes() {
    const origin = [0, 0, 0];
    arrow(origin, [1.35, 0, 0], colors.amber, 1.15, 5);
    arrow(origin, [0, 1.35, 0], colors.accent, 1.15, 5);
    arrow(origin, [0, 0, 1.35], colors.blue, 1.15, 5);
    labelAt('x [m]', [1.35, 0, 0], colors.amber, 4, 12);
    labelAt('y [m]', [0, 1.35, 0], colors.accent, 4, 12);
    labelAt('z [m]', [0, 0, 1.35], colors.blue, 4, -5);
  }

  function drawTracks() {
    for (const track of scene.tracks) {
      const coordinates = track.points
        .filter((point) => Math.hypot(point[0], point[1]) <= 3.72)
        .map((point) => point);
      const split = coordinates.findIndex((_, i) => track.path_m[i] > track.field_exit_path_m);
      const cut = split < 0 ? coordinates.length : split;
      const color = track.charge < 0 ? colors.accent : colors.amber;
      line(coordinates.slice(0, Math.max(cut + 1, 2)), color, 2.35, [], 1);
      if (cut < coordinates.length - 1) line(coordinates.slice(Math.max(cut - 1, 0)), color, 2.15, [5, 4], 0.9);
      if (cut < coordinates.length) {
        const p = project(coordinates[Math.min(cut, coordinates.length - 1)]);
        context.beginPath(); context.arc(p.x, p.y, 3, 0, Math.PI * 2);
        context.fillStyle = colors.blue; context.fill();
      }
      if (track.materialPoint) {
        const marker = project(track.materialPoint);
        context.beginPath(); context.arc(marker.x, marker.y, 4.2, 0, Math.PI * 2);
        context.fillStyle = colors.surface; context.fill();
        context.strokeStyle = colors.amber; context.lineWidth = 1.6; context.stroke();
        if (track.object_id === 0) labelAt('1 mm Si · s = 1 m', track.materialPoint, colors.amber, 7, -9);
      }
      const end = coordinates.at(-1);
      if (end) {
        labelAt(`μ${track.charge < 0 ? '−' : '+'} #${track.object_id}`, end, color, 5, -4);
        const endIndex = track.points.indexOf(end);
        if (endIndex > 0) arrow(track.points[endIndex - 1], end, color, 1.2, 5);
      }
    }
    const origin = project([0, 0, 0]);
    context.beginPath(); context.arc(origin.x, origin.y, 3, 0, Math.PI * 2);
    context.fillStyle = colors.ink; context.fill();
    context.beginPath(); context.arc(origin.x, origin.y, 5.5, 0, Math.PI * 2);
    context.strokeStyle = colors.ink; context.lineWidth = 1; context.stroke();
  }

  function render() {
    if (!scene || !cssWidth || !cssHeight) return;
    const style = getComputedStyle(document.documentElement);
    colors = {
      ink: style.getPropertyValue('--ink').trim(),
      surface: style.getPropertyValue('--surface').trim(),
      subtle: style.getPropertyValue('--subtle').trim(),
      line: style.getPropertyValue('--line').trim(),
      accent: style.getPropertyValue('--accent').trim(),
      amber: style.getPropertyValue('--amber').trim(),
      blue: style.getPropertyValue('--blue').trim(),
    };
    context.clearRect(0, 0, cssWidth, cssHeight);
    // Ground-plane one-metre grid; cylinders and paths remain in fixture metre coordinates.
    for (let n = -3; n <= 3; n++) {
      line([[-3.25, n, 0], [3.25, n, 0]], colors.line, 0.55, [], 0.35);
      line([[n, -3.25, 0], [n, 3.25, 0]], colors.line, 0.55, [], 0.35);
    }
    for (const surface of scene.geometry.surfaces) {
      if (surface.kind === 'cylinder' && surface.half_length_m) cylinder(surface);
      if (surface.kind === 'disk') circleAt(surface.outer_radius_m, surface.z_m, colors.subtle, 0.58, surface.inner_radius_m);
    }
    drawField();
    drawTracks();
    drawAxes();
    label.textContent = camera.label;
  }

  function setPreset(name) {
    camera = { ...presets[name], distance: camera.distance };
    for (const button of host.parentElement.querySelectorAll('[data-view-preset]')) {
      const active = button.dataset.viewPreset === name;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    render();
  }

  canvas.addEventListener('pointerdown', (event) => {
    pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!pointer || pointer.id !== event.pointerId) return;
    const dx = event.clientX - pointer.x;
    const dy = event.clientY - pointer.y;
    pointer.x = event.clientX; pointer.y = event.clientY;
    camera.azimuth -= dx * 0.008;
    camera.elevation = Math.max(-1.35, Math.min(1.52, camera.elevation + dy * 0.006));
    camera.label = 'Custom orbit';
    render();
  });
  canvas.addEventListener('pointerup', () => { pointer = null; });
  canvas.addEventListener('pointercancel', () => { pointer = null; });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    camera.distance = Math.max(10, Math.min(30, camera.distance * (event.deltaY > 0 ? 1.08 : 0.93)));
    render();
  }, { passive: false });
  canvas.addEventListener('keydown', (event) => {
    const step = 0.12;
    if (event.key === 'ArrowLeft') camera.azimuth -= step;
    else if (event.key === 'ArrowRight') camera.azimuth += step;
    else if (event.key === 'ArrowUp') camera.elevation = Math.min(1.52, camera.elevation + step);
    else if (event.key === 'ArrowDown') camera.elevation = Math.max(-1.35, camera.elevation - step);
    else if (event.key === '+' || event.key === '=') camera.distance = Math.max(10, camera.distance - 1);
    else if (event.key === '-') camera.distance = Math.min(30, camera.distance + 1);
    else if (event.key === '0') { setPreset('perspective'); return; }
    else return;
    event.preventDefault();
    camera.label = 'Custom orbit';
    render();
  });
  host.parentElement.querySelectorAll('[data-view-preset]').forEach((button) => {
    button.addEventListener('click', () => setPreset(button.dataset.viewPreset));
  });
  window.addEventListener('resize', resize);
  window.addEventListener('heplab:themechange', render);
  new ResizeObserver(resize).observe(host);

  fetch(fixtureUrl, { headers: { Accept: 'application/json' } })
    .then((response) => {
      if (!response.ok) throw new Error(`Fixture request returned ${response.status}`);
      return response.json();
    })
    .then((fixture) => {
      if (!fixture.artifact?.static_fixture || fixture.artifact?.schema !== 'heplab-run-artifact-v1') {
        throw new Error('The event is not a declared HEPLab synthetic fixture.');
      }
      const tracks = fixture.tracks.map((track) => ({
        object_id: track.object_id,
        charge: track.charge,
        points: track.trajectory.points,
        path_m: track.trajectory.path_m,
        field_exit_path_m: track.trajectory.field_exit_path_m,
        materialPoint: track.material?.state?.position,
      }));
      if (tracks.some((track) => track.points.length !== track.path_m.length || !track.field_exit_path_m)) {
        throw new Error('Trajectory points and path coordinates are incomplete.');
      }
      scene = { tracks, geometry: fixture.geometry };
      setStatus('Fixture loaded. Drag to orbit the scene.', 'ready');
      resize();
    })
    .catch((error) => setStatus(`3D view unavailable: ${error.message}. The synthetic event record remains available below.`, 'error'));
})();
