"""Exercise status transition safety without starting Textual or touching a DB."""
from types import SimpleNamespace
import unittest
import yaml
from unittest.mock import Mock, call, patch

from scripts.job_aggregator import tui


class ApplicationStatusTests(unittest.TestCase):
    def modal(self, cv_folder="test-role"):
        return SimpleNamespace(_initialized=True, app_id=42, current_status="1-Draft",
                               cv_folder=cv_folder, notify=Mock(), dismiss=Mock())

    def test_linked_applied_updates_before_snapshot(self):
        modal = self.modal()
        order = Mock()
        with patch("scripts.application.capture_sent_snapshot") as snapshot, patch.object(tui, "update_application") as update:
            order.attach_mock(snapshot, "snapshot")
            order.attach_mock(update, "update")
            order.attach_mock(modal.dismiss, "dismiss")
            tui.StatusModal.on_select_changed(modal, SimpleNamespace(value="2-Applied"))
        self.assertEqual(order.mock_calls, [
            call.update(42, status="2-Applied", _event_source="tui"),
            call.snapshot("test-role", source="tui"),
            call.dismiss(True),
        ])
        modal.notify.assert_not_called()

    def test_failed_snapshot_reports_saved_status_and_dismisses(self):
        for error in (ValueError("Rebuild before sending"), OSError("Archive unavailable"), yaml.YAMLError("Invalid YAML")):
            with self.subTest(error=error):
                modal = self.modal()
                with patch("scripts.application.capture_sent_snapshot", side_effect=error) as snapshot, patch.object(tui, "update_application") as update:
                    tui.StatusModal.on_select_changed(modal, SimpleNamespace(value="2-Applied"))
                snapshot.assert_called_once_with("test-role", source="tui")
                update.assert_called_once_with(42, status="2-Applied", _event_source="tui")
                modal.dismiss.assert_called_once_with(True)
                message = modal.notify.call_args.args[0]
                self.assertIn("Status saved", message)
                self.assertIn(str(error), message)
                self.assertIn("snapshot test-role --sent", message)
                self.assertEqual(modal.notify.call_args.kwargs, {"severity": "error", "timeout": 30})

    def test_unlinked_applied_updates_without_snapshot(self):
        modal = self.modal(cv_folder=None)
        with patch("scripts.application.capture_sent_snapshot") as snapshot, patch.object(tui, "update_application") as update:
            tui.StatusModal.on_select_changed(modal, SimpleNamespace(value="2-Applied"))
        snapshot.assert_not_called()
        update.assert_called_once_with(42, status="2-Applied", _event_source="tui")
        modal.dismiss.assert_called_once_with(True)

    def test_other_status_updates_without_snapshot(self):
        modal = self.modal()
        with patch("scripts.application.capture_sent_snapshot") as snapshot, patch.object(tui, "update_application") as update:
            tui.StatusModal.on_select_changed(modal, SimpleNamespace(value="3-Interview"))
        snapshot.assert_not_called()
        update.assert_called_once_with(42, status="3-Interview", _event_source="tui")
        modal.dismiss.assert_called_once_with(True)

    def test_initial_event_does_not_write(self):
        modal = self.modal()
        modal._initialized = False
        with patch("scripts.application.capture_sent_snapshot") as snapshot, patch.object(tui, "update_application") as update:
            tui.StatusModal.on_select_changed(modal, SimpleNamespace(value="2-Applied"))
        snapshot.assert_not_called()
        update.assert_not_called()
        modal.dismiss.assert_not_called()


if __name__ == "__main__":
    unittest.main()
