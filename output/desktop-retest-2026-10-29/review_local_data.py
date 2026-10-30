"""Read-only audit of the available extracts and a same-selection mass comparison."""
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import uproot

from heplab.physics.cms_mass_calibration import selected_pair

ROOT = Path('D:/HEPLab')
OUT = Path(__file__).resolve().parent
FOLDER = ROOT / 'artifacts/cms/measured'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


sources = {}
for name, filename, metadata in [
    ('recorded_cms', 'run2016g-100k.root', 'source.json'),
    ('official_cms_mc', 'dy-ul16-100k.root', 'dy-source.json'),
]:
    path = FOLDER / filename
    source = json.loads((FOLDER / metadata).read_text())
    checksum = digest(path)
    assert checksum == source['derived_file_sha256']
    with uproot.open(path) as file:
        entries = file['Events'].num_entries
    assert entries == source['entry_stop'] - source['entry_start'] == 100000
    sources[name] = dict(path=str(path), bytes=path.stat().st_size, entries=entries,
                         sha256=checksum, declared_source=source)

validation = json.loads((FOLDER / 'validation.json').read_text())
pairs_path = FOLDER / 'selected-pairs.json'
assert digest(pairs_path) == validation['selected_pairs_sha256']
data_rows = json.loads(pairs_path.read_text())
data_masses = np.array([row['mass_gev'] for row in data_rows])
assert len(data_masses) == validation['cutflow']['mass_window'] == 10863
edges = np.arange(60.0, 121.0)
assert np.histogram(data_masses, edges)[0].tolist() == (
    np.array(validation['histogram']['training']) + np.array(validation['histogram']['heldout'])
).tolist()

mc_masses = []
mc_cutflow = dict(input=0, trigger=0, two_selected_muons=0, mass_window=0)
seen = set()
with uproot.open(FOLDER / 'dy-ul16-100k.root') as file:
    names = ['run', 'luminosityBlock', 'event', 'genWeight', 'Muon_pt', 'Muon_eta',
             'Muon_phi', 'Muon_mass', 'Muon_charge', 'Muon_tightId', 'Muon_pfRelIso04_all',
             'HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ', 'HLT_Mu17_TrkIsoVVL_TkMu8_TrkIsoVVL_DZ']
    for chunk in file['Events'].iterate(names, step_size=10000, library='ak'):
        for event in chunk:
            mc_cutflow['input'] += 1
            assert float(event['genWeight']) == 1.0
            identity = tuple(int(event[k]) for k in ('run', 'luminosityBlock', 'event'))
            assert identity not in seen
            seen.add(identity)
            if not (bool(event[names[-1]]) or bool(event[names[-2]])):
                continue
            mc_cutflow['trigger'] += 1
            pair = selected_pair(event)
            if pair is None:
                continue
            mc_cutflow['two_selected_muons'] += 1
            if 60 <= pair['mass_gev'] < 120:
                mc_cutflow['mass_window'] += 1
                mc_masses.append(pair['mass_gev'])
assert len(mc_masses) == 11430
data = np.histogram(data_masses, edges)[0]
mc = np.histogram(mc_masses, edges)[0]
pd, pm = data / data.sum(), mc / mc.sum()
vd, vm = pd * (1 - pd) / data.sum(), pm * (1 - pm) / mc.sum()
ratio = np.divide(pd, pm, out=np.full_like(pd, np.nan), where=pm > 0)
rv = np.divide(vd, pm**2, out=np.full_like(pd, np.nan), where=pm > 0)
rv += np.divide(pd**2 * vm, pm**4, out=np.full_like(pd, np.nan), where=pm > 0)

with (OUT / 'recorded-vs-official-mc-mass.csv').open('w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['low_gev', 'high_gev', 'data_count', 'mc_count', 'data_fraction',
                     'mc_fraction', 'data_over_mc', 'statistical_ratio_error'])
    for i in range(len(data)):
        writer.writerow([edges[i], edges[i+1], data[i], mc[i], pd[i], pm[i],
                         ratio[i] if np.isfinite(ratio[i]) else '',
                         np.sqrt(rv[i]) if np.isfinite(rv[i]) else ''])

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
fig, (ax, lower) = plt.subplots(2,1,figsize=(9,7),sharex=True,
                              gridspec_kw={'height_ratios':[3,1]},layout='constrained')
centers = (edges[:-1] + edges[1:]) / 2
ax.stairs(pm, edges, color='#2464a0', linewidth=1.7, label='CMS DY full-simulation MC (11,430 pairs)')
ax.fill_between(centers, pm-np.sqrt(vm), pm+np.sqrt(vm), color='#2464a0', alpha=.15, step='mid')
ax.errorbar(centers, pd, yerr=np.sqrt(vd), fmt='o', markersize=3, color='#24303a',
            linewidth=.8, label='Recorded CMS Run2016G (10,863 pairs)')
ax.set_ylabel('Fraction of selected pairs / 1 GeV')
ax.set_title('Existing local CMS extracts: same-selection dimuon mass', loc='left', fontweight='bold')
ax.legend(frameon=False)
ax.grid(axis='y', alpha=.18)
lower.errorbar(centers, ratio, yerr=np.sqrt(rv), fmt='o', markersize=3, color='#24303a', linewidth=.8)
lower.axhline(1,color='#2464a0',linewidth=1)
lower.set(ylim=(0,2.5),xlim=(60,120),xlabel=r'$m_{\mu\mu}$ [GeV/$c^2$]',ylabel='Data / MC')
lower.grid(axis='y',alpha=.18)
fig.suptitle('Shape normalized separately • 100,000 source entries each • exploratory, no corrections',
             fontsize=10,color='#596772')
fig.savefig(OUT / 'recorded-vs-official-mc-mass.png',dpi=180)
plt.close(fig)

report = dict(sources=sources, recorded_cutflow=validation['cutflow'], mc_cutflow=mc_cutflow,
              selected_data_pairs=len(data_masses), selected_mc_pairs=len(mc_masses),
              selection=validation['selection'], data_pair_integrity_verified=True,
              histogram_reproduced=True, normalization='each selected population normalized to one',
              limitations=['One first-file projection per population; not all catalog data are downloaded',
                  'Full original source checksums are not verified; local derived-file hashes match',
                  'Trigger requirements and tight ID differ from the DELPHES generation workflow',
                  'No luminosity normalization, pileup reweighting or Rochester/efficiency corrections',
                  'No physics-systematic uncertainties; normalized bins are correlated',
                  'This comparison does not calibrate the detector or validate new PYTHIA runs'])
(OUT / 'local-data-review.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:report[k] for k in ('selected_data_pairs','selected_mc_pairs','recorded_cutflow','mc_cutflow')}),flush=True)
