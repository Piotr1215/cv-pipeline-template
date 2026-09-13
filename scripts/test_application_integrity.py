"""Hermetic regression tests for application files and input integrity."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import application


class ApplicationIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.apps = self.root / "applications"
        self.apps.mkdir()
        self.templates = self.root / "templates"
        self.templates.mkdir()
        self.patch_apps = patch.object(application, "APPLICATIONS_DIR", self.apps)
        self.patch_apps.start()
        self.addCleanup(self.patch_apps.stop)
        self.patch_templates = patch.object(application, "TEMPLATE_DIR", self.templates)
        self.patch_templates.start()
        self.addCleanup(self.patch_templates.stop)

    def scaffold(self, **kwargs):
        fields = dict(slug="test-role", company="Acme", role="Engineer", url="https://example.test",
                      location="Remote", salary="", source="manual", from_job=None,
                      variant="devops-engineer", force=False)
        fields.update(kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(application.cmd_new(SimpleNamespace(**fields)), 0)
        return application.app_dir(fields["slug"])

    def test_compile_preserves_user_files_and_isolates_auxiliary_files(self):
        folder = self.scaffold()
        (folder / "cv.tex").write_text("source")
        for name in ("interview-notes.md", "cover-letter.pdf", "private.log"):
            (folder / name).write_bytes(b"keep exactly")
        seen = []

        def compile_fake(command, *, cwd, **kwargs):
            seen.append(Path(cwd))
            self.assertNotEqual(Path(cwd), folder)
            self.assertEqual((Path(cwd) / "cv.tex").read_text(), "source")
            (Path(cwd) / "cv.pdf").write_bytes(b"new PDF")
            (Path(cwd) / "cv.aux").write_text("auxiliary")
            return SimpleNamespace(returncode=0, stdout="")

        with patch.object(application.subprocess, "run", side_effect=compile_fake):
            self.assertEqual(application._compile_pdf(folder), 0)
        self.assertEqual((folder / "cv.pdf").read_bytes(), b"new PDF")
        for name in ("interview-notes.md", "cover-letter.pdf", "private.log"):
            self.assertEqual((folder / name).read_bytes(), b"keep exactly")
        self.assertFalse((folder / "cv.aux").exists())
        self.assertFalse(seen[0].exists())

    def test_compile_failure_preserves_previous_pdf(self):
        folder = self.scaffold()
        (folder / "cv.tex").write_text("broken source")
        (folder / "cv.pdf").write_bytes(b"previous PDF")
        with patch.object(application.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="error")):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(application._compile_pdf(folder), 1)
        self.assertEqual((folder / "cv.pdf").read_bytes(), b"previous PDF")

    def test_scaffold_round_trips_yaml_special_characters(self):
        values = dict(company="Acme: Cloud #1", role="Engineer: Platform\nSenior", location="Remote # EU",
                      salary="EUR 80k: negotiable", source="manual: referral", url="https://example.test/#role")
        self.scaffold(**values)
        meta = application.load_application("test-role")["meta"]
        for key, value in values.items():
            self.assertEqual(meta[key], value)

    def test_rejects_unsafe_slugs(self):
        for slug in ("../escape", "/tmp/escape", "a/../../b", "a\\b", ".", "", "a--b"):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                application.app_dir(slug)

    def test_rejects_invalid_overrides(self):
        data = {"strengths": [{"title": "One"}]}
        spec = {"highlights": ["First"]}
        invalid = [[], {"typo": "value"}, {"profile_paras": "text"}, {"highlights": [123]},
                   {"experience_count": True}, {"experience_count": -1}, {"include_phone": "false"},
                   {"strength_indices": [1]}, {"strength_indices": [-1]}, {"strength_indices": [True]},
                   {"highlights_order": [1]}, {"highlights_order": "0"}, {"columnratio": 1},
                   {"sidebar_extras": [{"title": "missing text"}]},
                   {"tech_groups": [{"label": "Cloud", "tags": "AWS"}]}]
        for overrides in invalid:
            with self.subTest(overrides=overrides), patch.object(application, "build_spec", return_value=spec.copy()):
                with self.assertRaises(ValueError):
                    application.merged_spec(data, {"base": "devops-engineer", "overrides": overrides})

    def test_manifest_requires_matching_pdf_and_survives_yaml_drift(self):
        folder = self.scaffold()
        with self.assertRaisesRegex(ValueError, "Rebuild"):
            application.load_built_manifest("test-role")
        pdf = folder / "cv.pdf"
        pdf.write_bytes(b"built PDF")
        manifest = dict(version=1, pdf_hash=application._sha256_file(pdf),
                        composition={"highlights": ["original"], "role_type": "devops-engineer",
                                     "strength_indices": [], "strengths": [], "expertise_tags": [],
                                     "experience": [], "spec": {}},
                        date_generated="2026-01-01", overlay_yaml="base: devops-engineer\n")
        (folder / "build-manifest.json").write_text(json.dumps(manifest))
        (folder / "application.yaml").write_text("changed after build")
        self.assertEqual(application.load_built_manifest("test-role"), manifest)
        broken = dict(manifest)
        del broken["date_generated"]
        (folder / "build-manifest.json").write_text(json.dumps(broken))
        with self.assertRaisesRegex(ValueError, "Rebuild"):
            application.load_built_manifest("test-role")
        (folder / "build-manifest.json").write_text(json.dumps(manifest))
        pdf.write_bytes(b"different PDF")
        with self.assertRaisesRegex(ValueError, "Rebuild"):
            application.load_built_manifest("test-role")
        pdf.unlink()
        with self.assertRaisesRegex(ValueError, "Rebuild"):
            application.load_built_manifest("test-role")


if __name__ == "__main__":
    unittest.main()
