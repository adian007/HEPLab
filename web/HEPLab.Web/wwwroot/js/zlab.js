(() => {
  const root = document.querySelector(".zlab");
  if (!root) return;
  const nav = root.querySelector("#zlab-step-list");
  const stage = root.querySelector("#zlab-stage");
  const key = "heplab-z-lab-v1";
  const steps = [
    { id: "load", title: "Get oriented", sub: "Meet the events", task: "Check what is in this deterministic teaching sample. Every event is synthetic and generated offline.", hints: ["Start with the event count and the number of events containing a muon pair."] },
    { id: "select", title: "Choose muons", sub: "Make a selection", task: "Set pT ≥ 20 GeV, relative isolation ≤ 0.15, and require opposite charge. These exact cuts are used for the spectrum below.", hints: ["Z bosons are neutral, so the two muons have opposite charge.", "Use pT ≥ 20 GeV and isolation ≤ 0.15."] },
    { id: "mass", title: "Rebuild a mass", sub: "One event, by hand", task: "Reconstruct the invariant mass of these two muons. Work it out before entering your answer in GeV.", hints: ["For each muon, pz = pT sinh(η), px = pT cos(φ), and py = pT sin(φ).", "Add the four-vectors, then use m² = E² − |p|²."] },
    { id: "histogram", title: "Look for a peak", sub: "Many events together", task: "Apply the selection to the sample. Is the tallest mass bin above 50 GeV in the Z region?", hints: ["The Z peak is near 91 GeV.", "The histogram uses the selection you just entered."] },
    { id: "fit", title: "Measure the Z", sub: "Fit and uncertainty", task: "Read the fit report and enter the measured mass and statistical uncertainty. Compare your result with the PDG reference.", hints: ["The fitted mass should be close to 91.1876 GeV.", "A well-populated sample should give an uncertainty below 1 GeV."] },
    { id: "width", title: "Explain the width", sub: "What broadens the peak?", task: "The measured mass peak is wider than the Z boson’s natural width. What is the main reason in this dimuon measurement?", hints: ["Think about how precisely the detector measures each muon momentum."] }
  ];
  const fresh = () => ({ done: [], settings: { pt: 0, iso: 1, opposite: false }, selected: 0, hints: {} });
  let state;
  try { state = { ...fresh(), ...JSON.parse(localStorage.getItem(key) || "{}") }; } catch { state = fresh(); }
  state.done = Array.isArray(state.done) ? state.done : [];
  state.settings = { ...fresh().settings, ...state.settings };
  state.hints ||= {};
  const el = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([name, value]) => {
      if (name === "text") node.textContent = String(value);
      else if (name === "class") node.className = String(value);
      else if (name === "checked") node.checked = Boolean(value);
      else if (typeof value === "boolean") { if (value) node.setAttribute(name, ""); }
      else node.setAttribute(name, String(value));
    });
    node.append(...children);
    return node;
  };
  const persist = () => {
    try { localStorage.setItem(key, JSON.stringify(state)); root.querySelector("#zlab-save-label").textContent = "Saved just now"; }
    catch { root.querySelector("#zlab-save-label").textContent = "Progress stays in this tab"; }
  };
  const firstOpen = () => steps.findIndex(step => !state.done.includes(step.id));
  const feedback = (area, good, message) => {
    area.className = `zlab-feedback ${good ? "is-good" : "is-try"}`;
    area.textContent = `${good ? "Checkpoint complete · " : "Try again · "}${message}`;
    area.hidden = false;
  };
  const complete = (step, area, message) => {
    state.done = [...new Set([...state.done, step.id])];
    const next = firstOpen();
    state.selected = Math.min(next < 0 ? steps.length - 1 : next, steps.length - 1);
    persist();
    feedback(area, true, message);
    setTimeout(render, 450);
  };
  const field = (label, value, attrs = {}) => {
    const input = el("input", { class: "zlab-field", type: "number", value, "aria-label": label, ...attrs });
    return input;
  };
  const action = (text, handler, primary = true) => {
    const button = el("button", { class: primary ? "zlab-primary" : "zlab-secondary", type: "button", text });
    button.addEventListener("click", handler);
    return button;
  };
  const makeFeedback = () => el("div", { class: "zlab-feedback", hidden: true, "aria-live": "polite" });

  function draw(canvas, demo) {
    const context = canvas.getContext("2d");
    const width = canvas.clientWidth || 640, height = canvas.clientHeight || 210, ratio = devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = height * ratio; context.scale(ratio, ratio);
    const counts = demo.histogram.counts, max = Math.max(...counts) * 1.1, left = 35, bottom = 26;
    const style = getComputedStyle(root);
    context.strokeStyle = style.getPropertyValue("--sl-color-hairline"); context.fillStyle = style.getPropertyValue("--sl-color-gray-3"); context.font = "11px system-ui";
    for (let i = 0; i <= 4; i++) { const y = 8 + (height - bottom - 8) * i / 4; context.beginPath(); context.moveTo(left, y); context.lineTo(width - 8, y); context.stroke(); }
    counts.forEach((count, i) => { const x = left + (width - left - 8) * i / counts.length; const bar = (height - bottom - 8) * count / max; const edge = demo.histogram.edges[i]; context.fillStyle = edge > 86 && edge < 96 ? style.getPropertyValue("--sl-color-accent") : style.getPropertyValue("--sl-color-gray-4"); context.fillRect(x, height - bottom - bar, (width - left - 8) / counts.length - 1, bar); });
    for (let value = 40; value <= 140; value += 20) { const x = left + (width - left - 8) * (value - 40) / 100; context.fillStyle = style.getPropertyValue("--sl-color-gray-3"); context.fillText(`${value} GeV`, x - 16, height - 6); }
  }

  let demo;
  async function render() {
    if (!demo) {
      try {
        const response = await fetch("/assets/z-boson-demo.json");
        if (!response.ok) throw new Error("Sample unavailable");
        demo = await response.json();
      } catch {
        stage.replaceChildren(el("p", { text: "The synthetic teaching sample could not load. Check your connection and try again." }), action("Retry loading the sample", render));
        return;
      }
    }
    const doneCount = state.done.length;
    const step = steps[Math.max(0, Math.min(state.selected, steps.length - 1))];
    root.querySelector("#zlab-progress-label").textContent = `${doneCount} / ${steps.length}`;
    const progress = root.querySelector("[role=progressbar]");
    progress.setAttribute("aria-valuenow", String(doneCount));
    root.querySelector("#zlab-progress-fill").style.width = `${doneCount / steps.length * 100}%`;
    nav.replaceChildren();
    steps.forEach((item, index) => {
      const button = el("button", { class: `zlab-step-link${state.done.includes(item.id) ? " is-done" : ""}`, type: "button", "aria-label": `${index + 1}. ${item.title}`, "aria-current": index === state.selected ? "step" : "false", disabled: index > firstOpen() && !state.done.includes(item.id) });
      button.append(el("span", { class: "zlab-step-num", text: state.done.includes(item.id) ? "✓" : index + 1 }), el("span", { class: "zlab-step-copy" }, el("span", { class: "zlab-step-title", text: item.title }), el("span", { class: "zlab-step-sub", text: item.sub })));
      button.addEventListener("click", () => { state.selected = index; persist(); render(); });
      nav.append(button);
    });
    stage.replaceChildren(el("div", { class: "zlab-stage-top" }, el("span", { class: "zlab-overline", text: `Checkpoint ${String(state.selected + 1).padStart(2, "0")} / 06` }), el("span", { class: "zlab-saved", text: "Progress saved locally" })), el("h3", { class: "zlab-stage-title", text: step.title }), el("p", { class: "zlab-task", text: step.task }));
    const card = el("section", { class: "zlab-activity", "aria-label": "Checkpoint activity" });
    card.append(el("div", { class: "zlab-overline", text: "Your task" }));
    const result = makeFeedback();
    if (step.id === "load") {
      const metrics = el("div", { class: "zlab-metrics" }, el("div", { class: "zlab-metric" }, el("b", { text: demo.events.toLocaleString() }), el("span", { text: "synthetic practice events" })), el("div", { class: "zlab-metric" }, el("b", { text: demo.events_with_muon_pair.toLocaleString() }), el("span", { text: "events with a muon pair" })), el("div", { class: "zlab-metric" }, el("b", { text: "offline" }), el("span", { text: "no account or download required" })));
      card.append(metrics, el("div", { class: "zlab-actions" }, action("Load the practice sample", () => complete(step, result, `Loaded ${demo.events.toLocaleString()} events; ${demo.events_with_muon_pair.toLocaleString()} contain a muon pair.`))));
    } else if (step.id === "select") {
      const pt = field("Minimum muon transverse momentum in GeV", state.settings.pt, { min: 0, max: 100, step: 1 });
      const iso = field("Maximum relative isolation", state.settings.iso, { min: 0, max: 2, step: .05 });
      const opposite = el("input", { type: "checkbox", "aria-label": "Require opposite charge", checked: state.settings.opposite });
      card.append(el("label", { class: "zlab-form-row" }, el("span", { text: "Minimum muon pT" }), pt, el("span", { text: "GeV" })), el("label", { class: "zlab-form-row" }, el("span", { text: "Maximum relative isolation" }), iso), el("label", { class: "zlab-check-row" }, opposite, el("span", { text: "Require opposite charge" })));
      card.append(el("div", { class: "zlab-actions" }, action("Check my selection", () => {
        state.settings = { pt: Number(pt.value), iso: Number(iso.value), opposite: opposite.checked }; persist();
        const ok = state.settings.pt === 20 && state.settings.iso === .15 && state.settings.opposite;
        if (ok) complete(step, result, "Good choice: energetic, isolated, opposite-charge muons select neutral Z decays.");
        else feedback(result, false, "For this result use pT ≥ 20 GeV, relative isolation ≤ 0.15, and opposite charge.");
      })));
    } else if (step.id === "mass") {
      const muons = el("div", { class: "zlab-muons" });
      demo.muons.forEach((muon, index) => muons.append(el("div", { class: "zlab-muon" }, el("strong", { text: `Muon ${index + 1}` }), el("span", { text: `pT ${muon.pt.toFixed(2)} GeV · η ${muon.eta.toFixed(3)} · φ ${muon.phi.toFixed(3)} · q ${muon.charge > 0 ? "+" : "−"}` }))));
      const answer = field("Invariant mass in GeV", "", { step: ".001", placeholder: "e.g. 91.2" });
      card.append(muons, el("div", { class: "zlab-formula", text: "m² = (E₁ + E₂)² − |p⃗₁ + p⃗₂|²" }), el("label", { class: "zlab-form-row" }, el("span", { text: "Invariant mass" }), answer, el("span", { text: "GeV" })), el("div", { class: "zlab-actions" }, action("Check the mass", () => {
        const value = Number(answer.value);
        if (Number.isFinite(value) && Math.abs(value - demo.hand_mass_gev) / demo.hand_mass_gev <= .001) complete(step, result, `Correct. The reference calculation is ${demo.hand_mass_gev.toFixed(3)} GeV.`);
        else feedback(result, false, "Rebuild both four-vectors, including the muon mass, before adding them.");
      })));
    } else if (step.id === "histogram") {
      const canvas = el("canvas", { class: "zlab-chart", role: "img", "aria-label": "Dimuon mass histogram. Highlighted bins mark the Z mass region." });
      card.append(el("div", { class: "zlab-metrics" }, el("div", { class: "zlab-metric" }, el("b", { text: demo.histogram.entries.toLocaleString() }), el("span", { text: "selected pairs" })), el("div", { class: "zlab-metric" }, el("b", { text: "40–140" }), el("span", { text: "mass range · GeV" }))), el("div", { class: "zlab-chart-wrap" }, canvas), el("div", { class: "zlab-actions" }, action("Check the peak", () => {
        const index = demo.histogram.counts.reduce((best, count, current) => demo.histogram.edges[current] >= 50 && count > demo.histogram.counts[best] ? current : best, 0);
        const peak = (demo.histogram.edges[index] + demo.histogram.edges[index + 1]) / 2;
        if (demo.histogram.entries >= 200 && peak >= 86 && peak <= 96) complete(step, result, `The tallest bin is at ${peak.toFixed(1)} GeV. That is the Z boson.`);
        else feedback(result, false, "Check that your selection keeps the Z events.");
      })));
      requestAnimationFrame(() => draw(canvas, demo));
    } else if (step.id === "fit") {
      const mass = field("Fitted mass in GeV", "", { step: ".01", placeholder: "mass" });
      const error = field("Fit uncertainty in GeV", "", { step: ".01", placeholder: "uncertainty" });
      card.append(el("div", { class: "zlab-overline", text: "Gaussian + background fit report" }), el("div", { class: "zlab-metrics" }, el("div", { class: "zlab-metric" }, el("b", { text: demo.fit.values.mean.toFixed(2) }), el("span", { text: "fitted mass · GeV" })), el("div", { class: "zlab-metric" }, el("b", { text: demo.fit.errors.mean.toFixed(2) }), el("span", { text: "statistical uncertainty · GeV" })), el("div", { class: "zlab-metric" }, el("b", { text: demo.reference_mass_gev.toFixed(2) }), el("span", { text: "PDG reference mass · GeV" }))), el("label", { class: "zlab-form-row" }, el("span", { text: "Your result" }), mass, el("span", { text: "±" }), error, el("span", { text: "GeV" })), el("div", { class: "zlab-actions" }, action("Check the measurement", () => {
        const value = Number(mass.value), uncertainty = Number(error.value);
        if (Number.isFinite(value) && Number.isFinite(uncertainty) && uncertainty > 0 && Math.abs(value - demo.reference_mass_gev) <= 1 && uncertainty < 1) complete(step, result, `m = ${value.toFixed(2)} ± ${uncertainty.toFixed(2)} GeV, consistent with the reference.`);
        else feedback(result, false, "Report a mass within 1 GeV of the reference and an uncertainty below 1 GeV.");
      })));
    } else {
      const choices = [["a", "The Z boson lives long enough to broaden the peak."], ["b", "Finite muon momentum resolution broadens the reconstructed mass."], ["c", "The histogram bin width is the only source of broadening."], ["d", "The Z boson has no natural width."]];
      const group = el("div", { class: "zlab-choices", role: "group", "aria-label": "Why is the measured peak wider?" });
      let selected = "";
      choices.forEach(([value, text]) => { const button = el("button", { class: "zlab-choice", type: "button", "aria-pressed": "false", text: `${value.toUpperCase()} · ${text}` }); button.addEventListener("click", () => { selected = value; group.querySelectorAll("button").forEach(option => option.setAttribute("aria-pressed", String(option === button))); }); group.append(button); });
      card.append(group, el("div", { class: "zlab-actions" }, action("Submit answer", () => selected === "b" ? complete(step, result, "Exactly. The observed width combines the natural width with detector momentum resolution.") : feedback(result, false, "Consider how precisely the detector measures each muon."))));
    }

    const hint = el("div", { class: "zlab-hint", hidden: true });
    const hintButton = action("Need a hint?", () => { const hintIndex = state.hints[step.id] || 0; hint.textContent = step.hints[Math.min(hintIndex, step.hints.length - 1)]; hint.hidden = false; state.hints[step.id] = Math.min(hintIndex + 1, step.hints.length); persist(); }, false);
    card.append(el("div", { class: "zlab-actions" }, hintButton));
    stage.append(card, hint, result);
    if (state.done.length === steps.length) stage.append(el("section", { class: "zlab-completion" }, el("h4", { text: "You found the synthetic Z peak." }), el("p", { text: `The teaching-sample fit gives ${demo.fit.values.mean.toFixed(2)} ± ${demo.fit.errors.mean.toFixed(2)} GeV. You followed the chain from event selection to a mass measurement.` }), el("div", { class: "zlab-actions" }, el("a", { class: "zlab-primary", href: "/gallery/", text: "Explore the result gallery" }), el("a", { class: "zlab-secondary", href: "/reference/python-api-v1/", text: "Continue in Python" }))));
  }

  root.querySelector("#zlab-reset").addEventListener("click", () => { state = fresh(); persist(); render(); stage.focus(); });
  const redrawChart = () => { const canvas = root.querySelector('.zlab-chart'); if (canvas && demo) draw(canvas, demo); };
  document.addEventListener('heplab:theme', redrawChart);
  window.addEventListener('resize', redrawChart);
  render();
})();
