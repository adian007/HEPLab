import json
from pathlib import Path

WORKBENCH = Path(__file__).parents[1] / "src" / "heplab" / "server" / "static" / "workbench.js"


def test_preflight_names_the_selected_source_field_and_response_models():
    source = WORKBENCH.read_text(encoding="utf-8")
    assert "angular-muon-sample-v1 v1" in source
    assert "declared-muon-pair-v1 v1" in source
    assert "cms-tracker-oae-3.8t-v1 v1" in source
    assert "ideal-solenoid-helix-v1 v1" in source
    assert "delphes-reference-response-v1 v1" in source
    assert "const modelIds=`${sourceModelId} · ${fieldModelId}" in source


def test_selection_identity_is_typed_and_only_muons_highlight_trajectories():
    source = WORKBENCH.read_text(encoding="utf-8")
    assert "selected=track?{kind:'muon',event_id:selectionEventId(),object_id:id}:null" in source
    assert "selected={kind:`nanoaod:${group}`,event_id:selectionEventId()" in source
    assert (
        "function selectedTrackId(){return selected?.kind==='muon'?selected.object_id:null;}"
        in source
    )
    assert "selected:selectedTrackId()" in source
    assert "not shown as a trajectory" in source


def test_workbench_comparison_exports_provenance_and_plots_define_uncertainty():
    source = WORKBENCH.read_text(encoding="utf-8")
    markup = WORKBENCH.with_name("index.html").read_text(encoding="utf-8")
    assert "schema:'heplab-run-comparison-v1'" in source
    assert "result_sha256:value.artifact?.result_sha256??null" in source
    assert "group.set(event,(group.get(event)||0)+1)" in source
    assert "event-bin count²" in source
    assert all(f'id="{name}-plot-definition"' in markup for name in ("pt", "mass", "eta", "signal"))
    assert "Survival versus path · analytic exponential" in source
    assert "95% Wilson interval" in source
    assert "plotResponseEfficiency" in source
    assert "Matched relative pT residual" in markup
    assert 'id="xy-xz"' in markup
    assert 'id="linked-projection-pair"' in markup
    assert "projection==='xy-xz'" in source
    assert "Both views share selection, path cursor, pan and zoom" in source


def test_narrow_window_layout_is_reachable_in_the_packaged_desktop_config():
    config = json.loads(
        (Path(__file__).parents[1] / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    assert config["app"]["windows"][0]["minWidth"] == 800


def test_advanced_setup_is_collapsible_with_mode_aware_corrective_errors():
    markup = WORKBENCH.with_name("index.html").read_text(encoding="utf-8")
    source = WORKBENCH.read_text(encoding="utf-8")
    assert '<details id="bench-advanced" class="bench-settings advanced-settings">' in markup
    assert 'data-property="response"' in markup
    assert "its local pT dependence is unvalidated" in markup
    assert (
        'id="configuration-error" class="configuration-error" role="alert" aria-live="assertive"'
        in markup
    )
    assert "section.closest('details')?.setAttribute('open','')" in source
    assert "const firstInvalid=fields.map(id=>$(id))" in source
    assert ".find(input=>!input.disabled&&!input.checkValidity())" in source
    assert "${firstInvalid.validationMessage}" in source


def test_recorded_data_plots_expose_per_plot_population_units_and_covariance_scope():
    source = WORKBENCH.with_name("data-workspace.js").read_text(encoding="utf-8")
    assert "binCount=histogram.edges.length-1" in source
    assert "selected_events}/${value.events} events selected" in source
    assert "in ${units} from ${histogram.edges[0]}" in source
    assert "√(diagonal normalized-bin covariance), statistical only" in source
    assert "No luminosity scaling, efficiency or pileup corrections" in source
