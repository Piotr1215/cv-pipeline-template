"""Hermetic coverage for optional CV sections and PDF layout validation."""
import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate, generate_ats, test_data_completeness as completeness

ROOT = Path(__file__).resolve().parent.parent


class OptionalSectionsTest(unittest.TestCase):
    def test_optional_certifications_load_and_render(self):
        for content in (None, '', 'null\n', '[]\n'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp) / 'data'
                shutil.copytree(ROOT / 'data', data_dir)
                certs = data_dir / 'certifications.yaml'
                if content is None:
                    certs.unlink()
                else:
                    certs.write_text(content)
                for loader in (generate.load_yaml_data, generate_ats.load_yaml_data,
                               completeness.load_yaml_data):
                    self.assertEqual(loader(data_dir)['certifications'], [])
                data = generate.load_yaml_data(data_dir)
                for variant in generate.SPEC_BUILDERS:
                    latex = generate.render_cv(data, generate.build_spec(variant, data))
                    self.assertNotIn(r'\cvsection{Certifications}', latex)
                    self.assertNotIn('CERTIFICATIONS', generate_ats.generate_ats_cv(data, variant))
                    self.assertEqual(completeness.check_certifications(data, '', variant), [])

    def test_empty_languages_have_no_heading(self):
        original = generate.load_yaml_data(ROOT / 'data')
        for value in (None, []):
            data = copy.deepcopy(original)
            data['skills']['Languages'] = value
            for variant in generate.SPEC_BUILDERS:
                latex = generate.render_cv(data, generate.build_spec(variant, data))
                self.assertNotIn(r'\cvsection{Languages}', latex)
                self.assertNotIn('\nLanguages:', generate_ats.generate_ats_cv(data, variant))
        self.assertEqual(generate._languages({}), '')

    def test_zero_certification_limit_is_not_all(self):
        data = generate.load_yaml_data(ROOT / 'data')
        spec = generate.build_spec('devops-engineer', data)
        spec['cert_limit'] = 0
        self.assertNotIn(r'\cvsection{Certifications}', generate.render_cv(data, spec))
        with patch.object(completeness, 'build_spec', return_value=spec):
            self.assertEqual(completeness.check_certifications(data, '', 'devops-engineer'), [])
        self.assertTrue(completeness.check_certifications(data, '', 'devops-engineer'))

    def test_page_count(self):
        for output, success in [('Pages: 2\n', True), ('Pages: 1\n', False),
                                ('Pages: 3\n', False), ('', False), ('Pages: bad\n', False)]:
            with self.subTest(output=output), patch.object(completeness.subprocess, 'run') as run:
                run.return_value.stdout = output
                self.assertEqual(completeness.check_page_count(Path('cv.pdf')) == [], success)
        for error in (FileNotFoundError('pdfinfo'), subprocess.CalledProcessError(1, 'pdfinfo')):
            with patch.object(completeness.subprocess, 'run', side_effect=error):
                self.assertTrue(completeness.check_page_count(Path('cv.pdf')))

    def test_variant_fails_on_page_overflow(self):
        checks = ['check_personal_info', 'check_experience', 'check_education',
                  'check_strengths', 'check_skills', 'check_certifications']
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'devops-engineer.pdf').touch()
            from contextlib import ExitStack
            with ExitStack() as stack:
                for check in checks:
                    stack.enter_context(patch.object(completeness, check, return_value=[]))
                stack.enter_context(patch.object(completeness, 'get_pdf_text', return_value='text'))
                run = stack.enter_context(patch.object(completeness.subprocess, 'run'))
                run.return_value.stdout = 'Pages: 3\n'
                self.assertFalse(completeness.test_variant('devops-engineer', ROOT / 'data', Path(tmp)))


if __name__ == '__main__':
    unittest.main()
