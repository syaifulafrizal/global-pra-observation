#!/usr/bin/env python3
"""Record the deliberately limited method change against the prior source revision."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess


def verify(baseline):
    def previous(path):
        return subprocess.check_output(['git', 'show', f'{baseline}:{path}'])

    def functions(source):
        return {node.name: ast.dump(node, include_attributes=False)
                for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}

    old = functions(previous('pra_nighttime.py'))
    new = functions(Path('pra_nighttime.py').read_bytes())
    unchanged = ['read_iaga2002', 'spectral_setup', 'multitaper_psd', 'compute_pseries',
                 'fit_evt_threshold', 'fit_ksigma_threshold', 'nz_guard',
                 'persistence_rule', 'historical_z_stats', 'save_plot']
    for name in unchanged:
        assert old[name] == new[name], f'Unexpected method change: {name}'
    preserved_files = ['earthquake_integration.py', 'integrate_earthquakes.py',
                       'deploy_all.bat', 'deploy_all.ps1', 'run_daily_analysis.bat',
                       'run_daily_analysis.ps1', 'deploy_to_github.ps1',
                       'validate_pages_output.py']
    hashes = {}
    for name in preserved_files:
        content = Path(name).read_bytes()
        # Git text normalization can differ from a Windows working copy.
        normalize = lambda value: value.replace(b'\r\n', b'\n')
        assert normalize(content) == normalize(previous(name)), f'Unexpected change: {name}'
        hashes[name] = hashlib.sha256(normalize(content)).hexdigest()
    export_before = functions(previous('upload_results.py'))
    export_after = functions(Path('upload_results.py').read_bytes())
    for name in ('get_available_dates', 'build_aggregated_data'):
        assert export_before[name] == export_after[name], f'Unexpected export data change: {name}'
    return {
        'baseline_commit': subprocess.check_output(['git', 'rev-parse', baseline], text=True).strip(),
        'unchanged_functions': unchanged,
        'unchanged_files_sha256_lf': hashes,
        'unchanged_export_functions': ['get_available_dates', 'build_aggregated_data'],
        'intentional_changes': [
            'Threshold samples: 13 previous local nights plus the observation night',
            'Unavailable/insufficient SYM-H: assume quiet and preserve absent-coverage provenance',
            'Historical P eligibility: accept stored assumed-quiet decisions',
            'Retain 14 nights of JSON; existing CSV/figure and dashboard windows unchanged',
            'Version 3 output records baseline window, contributing nights, samples and quiet policy',
            'Dashboard explains the policy and actual baseline coverage; larger responsive map',
            'Known INTERMAGNET unknown-observatory responses stay unavailable without aborting publication of other stations; other failures still fail',
            'Dashboard individual-file fallback matches aggregate dates and validity; absent optional earthquake summaries export explicit unknown counts',
        ],
        'expected_effect': 'Thresholds, eligible hours and resulting anomaly flags may change. Existing observations are not recomputed.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='888cf9441ff87d99185a329c7fa157da0e3e9729')
    parser.add_argument('--output', type=Path, default=Path('output/dogfood/method-2026-10-20/method-impact.json'))
    args = parser.parse_args()
    result = verify(args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Preservation checks passed: {len(result["unchanged_functions"])} functions, {len(result["unchanged_files_sha256_lf"])} files')
