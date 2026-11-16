#!/usr/bin/env python3
"""Hermetic regressions for status authority, exports and submission failures."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import yaml
from scripts import application
from scripts.job_aggregator import storage


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.patches = [patch.object(storage, 'DB_PATH', root / 'jobs.db'),
                        patch.object(application, 'APPLICATIONS_DIR', root / 'applications')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        folder = root / 'applications' / 'example'
        folder.mkdir(parents=True)
        self.path = folder / 'application.yaml'
        self.path.write_text('''meta:
  company: Example
  role: Manager
  status: draft  # preserve this comment
  applied_on:
  notes: |
    status: this is prose, not a field to update
base: devops-engineer
overrides: {}
''')
        storage.init_db()
        application.sync_to_board()
        self.board = storage.get_application_by_cv_folder('example')

    def test_live_status_and_export_preserve_content(self):
        original = self.path.read_text()
        storage.update_application(self.board['id'], status='4-Interview', date_applied='2026-09-13')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            application.cmd_status(SimpleNamespace())
        self.assertIn('interview', output.getvalue())
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(application.cmd_export_status(SimpleNamespace(check=True)), 1)
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(application.cmd_export_status(SimpleNamespace(check=False)), 0)
        self.assertEqual(application.cmd_export_status(SimpleNamespace(check=True)), 0)
        text = self.path.read_text()
        self.assertIn('# preserve this comment', text)
        self.assertIn('status: this is prose', text)
        meta = yaml.safe_load(text)['meta']
        self.assertEqual(meta['status'], 'interview')
        self.assertEqual(str(meta['applied_on']), '2026-09-13')
        application.sync_to_board()
        self.assertEqual(storage.get_application_by_cv_folder('example')['status'], '4-Interview')

    def test_export_inserts_missing_fields_and_handles_stale_archived(self):
        self.path.write_text(self.path.read_text().replace('  status: draft  # preserve this comment\n', '').replace('  applied_on:\n', ''))
        storage.update_application(self.board['id'], status='92-Stale')
        storage.archive_application(self.board['id'])
        self.assertEqual(application.cmd_export_status(SimpleNamespace(check=False)), 0)
        self.assertEqual(application.cmd_export_status(SimpleNamespace(check=True)), 0)
        meta = yaml.safe_load(self.path.read_text())['meta']
        self.assertEqual(meta['status'], 'stale')
        self.assertIsNone(meta['applied_on'])

    def test_export_unknown_board_does_not_seed(self):
        storage.delete_application(self.board['id'])
        self.assertEqual(application.cmd_export_status(SimpleNamespace(check=True)), 1)
        self.assertIsNone(storage.get_application_by_cv_folder('example'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            application.cmd_status(SimpleNamespace())
        self.assertIn('draft*', output.getvalue())
        self.assertIsNone(storage.get_application_by_cv_folder('example'))

    def test_export_unknown_status_reports_and_preserves_yaml(self):
        original = self.path.read_text()
        storage.update_application(self.board['id'], status='99-Unexpected')
        for check in (True, False):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                self.assertEqual(application.cmd_export_status(SimpleNamespace(check=check)), 1)
            self.assertIn("unsupported board status '99-Unexpected'", output.getvalue())
            self.assertEqual(self.path.read_text(), original)

    def test_cli_snapshot_failure_is_nonzero_and_recorded(self):
        original = self.path.read_text()
        with patch.object(application, 'snapshot_application', side_effect=OSError('disk full')):
            self.assertEqual(application.cmd_set_status(SimpleNamespace(slug='example', status='applied')), 1)
        self.assertEqual(storage.get_application_by_cv_folder('example')['status'], '2-Applied')
        self.assertEqual(self.path.read_text(), original)
        events = storage.get_events(self.board['id'])
        self.assertEqual([e['event_type'] for e in events], ['applied', 'snapshot failed'])
        self.assertIn('disk full', events[-1]['note'])

    def test_none_snapshot_is_failure(self):
        with patch.object(application, 'snapshot_application', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'no snapshot'):
                application.capture_sent_snapshot('example', source='test')
        self.assertEqual(storage.get_events(self.board['id'])[-1]['event_type'], 'snapshot failed')

    def test_date_preserved_and_draft_not_counted_as_sent(self):
        storage.update_application(self.board['id'], status='2-Applied', date_applied='2026-09-13')
        storage.update_application(self.board['id'], status='2-Applied')
        draft = application.snapshot_application('example')
        with patch.object(application, "load_built_manifest", return_value={"composition": application.resolve_composition(application.load_yaml_data(application.DATA_DIR), application.load_application("example")), "pdf_hash": "abc", "overlay_yaml": self.path.read_text(), "date_generated": "2026-09-13"}), patch.object(application, "_archive_build", return_value=Path("/tmp/archived.pdf")):
            sent = application.snapshot_application('example', sent=True)
        snapshots = {s['id']: s for s in storage.get_snapshots(self.board['id'])}
        self.assertIsNone(snapshots[draft]['date_applied'])
        self.assertEqual(snapshots[sent]['date_applied'], '2026-09-13')

    def test_tui_failure_notifies_and_blank_selection_is_ignored(self):
        from textual.widgets import Select
        from scripts.job_aggregator.tui import StatusModal
        modal = StatusModal(self.board['id'], '1-Open', 'example')
        modal._initialized = True
        with patch.object(modal, 'notify') as notify, patch.object(modal, 'dismiss') as dismiss:
            modal.on_select_changed(SimpleNamespace(value=Select.BLANK))
            dismiss.assert_not_called()
            with patch.object(application, 'snapshot_application', side_effect=OSError('disk full')):
                modal.on_select_changed(SimpleNamespace(value='2-Applied'))
            self.assertEqual(notify.call_args.kwargs['severity'], 'error')
            self.assertIn('snapshot example --sent', notify.call_args.args[0])
            dismiss.assert_called_once_with(True)
        self.assertEqual(storage.get_events(self.board['id'])[-1]['event_type'], 'snapshot failed')


if __name__ == '__main__':
    unittest.main()
