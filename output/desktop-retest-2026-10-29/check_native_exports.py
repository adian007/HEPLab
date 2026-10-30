"""Check actual native downloads against independently read ROOT branches."""
import csv
import json
from pathlib import Path

import awkward as ak
import numpy as np
import uproot

OUT = Path(__file__).resolve().parent
DOWNLOADS = Path('C:/Users/adian/Downloads')
ID = 'eff23414f8fe0659c0501cab'
base = DOWNLOADS / f'heplab-{ID}'
result = json.loads(Path(str(base) + '-event-0.json').read_text())
selected = json.loads(Path(str(base) + '-event-3.json').read_text())
rows = list(csv.DictReader(Path(str(base) + '-events.csv').open()))
assert len(rows) == result['summary']['events'] == 100
assert len({row['event'] for row in rows}) == 100
assert sum(row['passes_selection'] == 'true' for row in rows) == 33
assert selected['event'] == 3 and selected['event_info']['selected']
assert selected['analysis'] == result['analysis']
assert selected['artifact']['run_id'] == result['artifact']['run_id'] == ID
with uproot.open(Path(result['output_directory']) / 'events.root') as source:
    tree = source['Delphes']
    assert tree.num_entries == len(rows)
    arrays = tree.arrays(['Muon.PT', 'Muon.Eta', 'Jet.PT', 'MissingET.MET', 'Event.Weight'])
    for i, row in enumerate(rows):
        assert int(row['event']) == i
        assert int(row['reconstructed_muons']) == len(arrays['Muon.PT'][i])
        assert int(row['jets']) == len(arrays['Jet.PT'][i])
        assert np.isclose(float(row['missing_pt_gev']), float(arrays['MissingET.MET'][i][0]),
                          rtol=1e-14, atol=1e-12)
        assert float(row['weight']) == float(arrays['Event.Weight'][i][0])
    for track, pt in zip(selected['tracks'], arrays['Muon.PT'][3], strict=True):
        assert np.isclose(track['detector']['pt'], float(pt), rtol=1e-14, atol=1e-12)
    populations = {
        'pt': ak.to_numpy(ak.flatten(arrays['Muon.PT'])),
        'eta': ak.to_numpy(ak.flatten(arrays['Muon.Eta'])),
        'met': ak.to_numpy(ak.flatten(arrays['MissingET.MET'])),
        'mass': np.array([float(row['candidate_mass_gev']) for row in rows if row['candidate_mass_gev']]),
    }
    for key, values in populations.items():
        histogram = result['analysis']['histograms'][key]
        edges = np.asarray(histogram['edges'])
        counts, _ = np.histogram(values[values < edges[-1]], edges)
        expected = [int((values < edges[0]).sum()), *counts.tolist(), int((values >= edges[-1]).sum())]
        assert histogram['entries_with_flow'] == expected, key
        assert histogram['sumw_with_flow'] == expected, key  # this stream has unit weights
    assert sum(result['analysis']['histograms']['pt']['entries_with_flow']) == 113
    assert sum(result['analysis']['histograms']['met']['entries_with_flow']) == 100
report = dict(status='passed', native_run_id=ID, events=100, reconstructed_muons=113,
              selected_events=33, plots_checked_against_root=list(populations),
              csv_checked_against_root=True, selected_event_export=3,
              selected_event_preserves_run_analysis=True,
              ui_navigation_observed=[0,1,0,3,2,6], empty_muon_event=6,
              float_comparison_tolerance=dict(rtol=1e-14,atol_gev=1e-12),
              software_check_scope='ROOT counts and native exports; not physics-model validation')
(OUT / 'native-export-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
