"""Unattended workflow and operational logging regression checks, without network or Git writes."""
import io
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from logging_utils import attach_stdout_logger

ROOT = Path(__file__).resolve().parents[1]


class DeploymentSafety(unittest.TestCase):
    def test_default_logging_includes_download_warnings_and_station_summary(self):
        output = io.StringIO()
        logger = logging.Logger('deployment-fixture', level=logging.INFO)
        logger.addHandler(logging.StreamHandler(output))
        with patch('builtins.print'):
            attach_stdout_logger(logger)
            print('Warning: Download failed for TUC: reset 10054')
            print('Summary:')
            print('  TUC: failed')
            print('  Failed/Error: 1')
        self.assertIn('reset 10054', output.getvalue())
        self.assertIn('TUC: failed', output.getvalue())
        self.assertIn('Failed/Error: 1', output.getvalue())

    @unittest.skipUnless(os.name == 'nt', 'Windows workflow wrappers')
    def test_batch_finishes_without_input_and_propagates_stage_failures(self):
        stages = ['ensure_station_data.py', 'pra_nighttime.py',
                  'integrate_earthquakes.py', 'upload_results.py', 'deploy_to_github.ps1']
        for failed in (None, 'pra_nighttime.py', 'upload_results.py', 'deploy_to_github.ps1'):
            with self.subTest(failed_stage=failed), tempfile.TemporaryDirectory(prefix='gempra-unattended-') as tmp:
                folder = Path(tmp)
                for name in ('deploy_all.bat', 'deploy_all.ps1'):
                    shutil.copy2(ROOT / name, folder / name)
                for name in stages[:-1]:
                    source = "from pathlib import Path\nimport json\nwith Path('stages.txt').open('a') as f: f.write(" + repr(name + '\n') + ")\n"
                    if name == 'upload_results.py':
                        source += "Path('web_output/data').mkdir(parents=True, exist_ok=True)\nPath('web_output/data/stations.json').write_text(json.dumps({'stations':['KAK','HON']}))\n"
                    source += f'raise SystemExit({7 if name == failed else 0})\n'
                    (folder / name).write_text(source, encoding='utf-8')
                (folder / stages[-1]).write_text("Add-Content stages.txt 'deploy_to_github.ps1'\n$global:LASTEXITCODE = " + ('7' if failed == stages[-1] else '0') + '\n', encoding='utf-8')
                env = os.environ.copy()
                env.pop('FORCE_RERUN', None)
                result = subprocess.run(['cmd.exe', '/d', '/c', str(folder / 'deploy_all.bat')],
                                        cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, errors='replace', timeout=30)
                reached = (folder / 'stages.txt').read_text().splitlines()
                expected = stages if failed is None else stages[:stages.index(failed) + 1]
                self.assertEqual(reached, expected, result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0 if failed is None else 1, result.stdout + result.stderr)
                self.assertNotIn('Read-Host', result.stderr)
                self.assertNotIn('Press Enter', result.stdout)
                self.assertNotIn('Press any key', result.stdout)
                if failed:
                    self.assertNotIn('Workflow Completed!', result.stdout)
