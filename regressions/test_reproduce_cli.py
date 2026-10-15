"""Help must not run scientific checks or write hardening results."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('workflow_reproduce_cli', ROOT / 'reproduce.py')
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class ReproduceCliTests(unittest.TestCase):
    def test_help_stops_after_core_parser(self):
        for flags in (['--help'], ['-h'], ['--quick', '--help']):
            with self.subTest(flags=flags), \
                 patch.object(sys, 'argv', [str(ROOT / 'reproduce.py'), *flags]), \
                 patch.object(ENTRY, 'run') as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(ENTRY.main(), 0)
                run.assert_called_once_with([sys.executable, str(ROOT / '_reproduce_core.py'), *flags])
                self.assertEqual(output.getvalue(), '')

    def test_quick_and_full_still_run_hardening(self):
        for flags in ([], ['--quick']):
            with self.subTest(flags=flags), \
                 patch.object(sys, 'argv', [str(ROOT / 'reproduce.py'), *flags]), \
                 patch.object(ENTRY, 'run') as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ENTRY.main(), 0)
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args_list[0].args[0],
                                 [sys.executable, str(ROOT / '_reproduce_core.py'), *flags])
                self.assertEqual(run.call_args_list[1].args[0],
                                 [sys.executable, str(ROOT / 'src/reviewer_hardening.py'), *flags])


if __name__ == '__main__':
    unittest.main()
