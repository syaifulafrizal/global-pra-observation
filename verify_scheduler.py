#!/usr/bin/env python3
"""Rehearse existing Windows workflow wrappers in isolation with inert stage fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def verify(destination='output/dogfood/optimization'):
    if os.name != 'nt':
        raise SystemExit('This rehearsal requires Windows PowerShell and cmd.exe')
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    reports = []
    root = Path.cwd()
    for entrypoint in ('deploy_all.bat', 'run_daily_analysis.bat'):
        with tempfile.TemporaryDirectory(prefix='gempra-scheduler-rehearsal-') as temporary:
            fixture = Path(temporary)
            for name in ('deploy_all.bat', 'deploy_all.ps1', 'run_daily_analysis.bat', 'run_daily_analysis.ps1'):
                shutil.copy2(root / name, fixture / name)
            for name in ('ensure_station_data.py', 'pra_nighttime.py', 'integrate_earthquakes.py', 'upload_results.py'):
                script = "from pathlib import Path\nimport json\nwith Path('stages.txt').open('a') as f: f.write(" + repr(name + '\n') + ")\n"
                if name == 'upload_results.py':
                    script += "Path('web_output/data').mkdir(parents=True, exist_ok=True)\nPath('web_output/data/stations.json').write_text(json.dumps({'stations':['KAK','HON']}))\n"
                (fixture / name).write_text(script, encoding='utf-8')
            (fixture / 'deploy_to_github.ps1').write_text("Add-Content stages.txt 'deploy_to_github.ps1'\n$global:LASTEXITCODE = 0\n", encoding='utf-8')
            env = os.environ.copy()
            env.pop('GITHUB_REPO', None)
            env.pop('FORCE_RERUN', None)
            env['PATH'] = str(Path(os.sys.executable).parent) + os.pathsep + env['PATH']
            completed = subprocess.run(['cmd.exe', '/d', '/c', str(fixture / entrypoint)],
                                       cwd=fixture, env=env, input='\n\n\n',
                                       capture_output=True, text=True, errors='replace', timeout=60)
            stages = (fixture / 'stages.txt').read_text().splitlines()
            expected = ['pra_nighttime.py', 'integrate_earthquakes.py', 'upload_results.py']
            if entrypoint == 'deploy_all.bat':
                expected = ['ensure_station_data.py'] + expected + ['deploy_to_github.ps1']
            assert completed.returncode == 0, completed.stdout + completed.stderr
            assert stages == expected, stages
            (destination / f'{entrypoint}-rehearsal.log').write_text(completed.stdout + completed.stderr, encoding='utf-8')
            reports.append({'entrypoint': entrypoint, 'exit_code': completed.returncode,
                            'stages': stages, 'fixture_only': True})
    (destination / 'scheduler-rehearsal.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    verify()
