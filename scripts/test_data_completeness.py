#!/usr/bin/env python3
"""
Test script to verify all YAML data is rendered in generated PDFs.
Checks that all jobs, skills, certifications, education entries appear in the output.
"""

import yaml
import subprocess
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any

# Make `scripts.generate` importable when run directly (python3 scripts/test_data_completeness.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.generate import SPEC_BUILDERS, build_spec  # noqa: E402

def load_yaml_data(data_dir: Path) -> Dict[str, Any]:
    """Load all YAML data files."""
    data = {}
    for yaml_file in data_dir.glob('*.yaml'):
        with open(yaml_file) as f:
            data[yaml_file.stem] = yaml.safe_load(f)
    return data

def get_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF using pdftotext."""
    try:
        result = subprocess.run(
            ['pdftotext', str(pdf_path), '-'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""

def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, collapse whitespace, unfold ligatures and quotes).

    pdflatex emits fi/fl/ff/ffi/ffl as single Unicode ligature glyphs, so "Certified"
    extracts as "Certiﬁed". Unfold them or every word containing one fails the check.
    """
    ligature_map = {
        '\ufb01': 'fi', '\ufb02': 'fl', '\ufb00': 'ff',
        '\ufb03': 'ffi', '\ufb04': 'ffl',
        '\u00ad': '',  # soft hyphen (optional line break)
    }
    for ligature, replacement in ligature_map.items():
        text = text.replace(ligature, replacement)
    # Normalize various apostrophe/quote characters to standard ones using Unicode
    text = text.replace('\u2019', "'")  # Right single quotation mark
    text = text.replace('\u2018', "'")  # Left single quotation mark
    text = text.replace('\u201c', '"')  # Left double quotation mark
    text = text.replace('\u201d', '"')  # Right double quotation mark
    return ' '.join(text.lower().split())

def check_experience(data: Dict, pdf_text: str, variant: str) -> List[str]:
    """Check that all job experiences are present."""
    issues = []
    pdf_normalized = normalize_text(pdf_text)

    # All variants share the 2-page layout: first 5 roles render on page 2.
    exp_limit = 5
    for idx, job in enumerate(data['experience'][:exp_limit]):
        job_title = normalize_text(job['title'])
        company = normalize_text(job['company'])

        if job_title not in pdf_normalized:
            issues.append(f"Missing job title: {job['title']}")
        if company not in pdf_normalized:
            issues.append(f"Missing company: {job['company']}")

        # Check at least first achievement is present
        if job['achievements'] and len(job['achievements']) > 0:
            first_achievement = normalize_text(job['achievements'][0])
            # Check for partial match (first 30 chars)
            if first_achievement[:30] not in pdf_normalized:
                issues.append(f"Missing achievement from {job['company']}: {job['achievements'][0][:50]}...")

    return issues

def check_skills(data: Dict, pdf_text: str, variant: str) -> List[str]:
    """Check that skills are present."""
    issues = []
    pdf_normalized = normalize_text(pdf_text)

    # Check programming languages
    if 'Programming Languages' in data['skills']:
        for skill in data['skills']['Programming Languages'][:6]:
            skill_normalized = normalize_text(skill)
            if skill_normalized not in pdf_normalized:
                issues.append(f"Missing programming language: {skill}")

    # Check DevOps/Cloud technologies
    if 'DevOps and Cloud Technologies' in data['skills']:
        for skill in data['skills']['DevOps and Cloud Technologies'][:8]:
            skill_normalized = normalize_text(skill)
            if skill_normalized not in pdf_normalized:
                issues.append(f"Missing DevOps/Cloud tech: {skill}")

    return issues

def check_education(data: Dict, pdf_text: str, variant: str) -> List[str]:
    """Check that education entries are present."""
    issues = []
    pdf_normalized = normalize_text(pdf_text)

    for edu in data['education']:
        # Check for substring match of degree (may have specialization appended)
        degree_normalized = normalize_text(edu['degree'])
        degree_found = degree_normalized in pdf_normalized

        institution = normalize_text(edu['institution'])

        if not degree_found:
            issues.append(f"Missing degree: {edu['degree']}")
        if institution not in pdf_normalized:
            issues.append(f"Missing institution: {edu['institution']}")

    return issues

def check_certifications(data: Dict, pdf_text: str, variant: str) -> List[str]:
    """Check that certifications are present."""
    issues = []
    pdf_normalized = normalize_text(pdf_text)

    # Each variant's spec decides how many certifications render (None = all).
    cert_limit = build_spec(variant, data).get('cert_limit') or len(data['certifications'])

    for cert in data['certifications'][:cert_limit]:
        cert_name = normalize_text(cert['name'])
        if cert_name not in pdf_normalized:
            issues.append(f"Missing certification: {cert['name']}")

    return issues

def check_personal_info(data: Dict, pdf_text: str, variant: str) -> List[str]:
    """Check that personal information is present."""
    issues = []
    pdf_normalized = normalize_text(pdf_text)

    personal = data['personal']

    # Check name
    full_name = normalize_text(f"{personal['first_name']} {personal['last_name']}")
    if full_name not in pdf_normalized:
        issues.append(f"Missing name: {personal['first_name']} {personal['last_name']}")

    # Check email (without mailto:)
    email = normalize_text(personal['email'])
    if email not in pdf_normalized:
        issues.append(f"Missing email: {personal['email']}")

    # Check tagline for variant
    if variant in personal['taglines']:
        tagline = normalize_text(personal['taglines'][variant])
        if tagline not in pdf_normalized:
            issues.append(f"Missing tagline: {personal['taglines'][variant]}")

    return issues

def check_strengths(data: Dict, pdf_text: str, variant: str) -> List[str]:
    """Check that strengths/core competencies are present."""
    issues = []
    pdf_normalized = normalize_text(pdf_text)

    # Each variant's spec selects role-tailored strengths by index into strengths.yaml.
    indices = build_spec(variant, data)['strength_indices']
    selected = [data['strengths'][i] for i in indices if i < len(data['strengths'])]

    for strength in selected:
        title_normalized = normalize_text(strength['title'])

        # Check if title appears as exact substring OR all words are present
        # (PDF text extraction may reorder due to columns/layout)
        title_found = title_normalized in pdf_normalized
        if not title_found:
            # Fallback: check if all significant words (>3 chars) are present
            title_words = [w for w in title_normalized.split() if len(w) > 3]
            title_found = all(word in pdf_normalized for word in title_words)

        if not title_found:
            issues.append(f"Missing strength title: {strength['title']}")

        # Check description is present (at least first 30 chars)
        desc = normalize_text(strength['description'])
        if desc[:30] not in pdf_normalized:
            issues.append(f"Missing strength description: {strength['title']}")

    return issues

def test_variant(variant: str, data_dir: Path, output_dir: Path) -> bool:
    """Test a single CV variant."""
    print(f"\n{'='*60}")
    print(f"Testing variant: {variant}")
    print(f"{'='*60}")

    # Load data
    data = load_yaml_data(data_dir)

    # Get PDF path
    pdf_path = output_dir / f"{variant}.pdf"
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        return False

    # Extract PDF text
    pdf_text = get_pdf_text(pdf_path)
    if not pdf_text:
        print(f"❌ Could not extract text from PDF")
        return False

    # Run all checks
    all_issues = []

    print("\n📋 Checking personal information...")
    issues = check_personal_info(data, pdf_text, variant)
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All personal info present")

    print("\n💼 Checking experience...")
    issues = check_experience(data, pdf_text, variant)
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All experience entries present")

    print("\n🎓 Checking education...")
    issues = check_education(data, pdf_text, variant)
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All education entries present")

    print("\n🏆 Checking strengths...")
    issues = check_strengths(data, pdf_text, variant)
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All strengths present")

    print("\n💻 Checking skills...")
    issues = check_skills(data, pdf_text, variant)
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All skills present")

    print("\n📜 Checking certifications...")
    issues = check_certifications(data, pdf_text, variant)
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ All certifications present")

    # Summary
    print(f"\n{'='*60}")
    if all_issues:
        print(f"❌ FAILED: {len(all_issues)} issues found")
        return False
    else:
        print(f"✅ PASSED: All data present in {variant} PDF")
        return True

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description='Test CV data completeness')
    parser.add_argument('--variant', help='Test specific variant only')
    args = parser.parse_args()

    # Setup paths
    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / 'data'
    output_dir = root_dir / 'output' / 'generated'

    if args.variant:
        variants = [args.variant]
    else:
        variants = list(SPEC_BUILDERS)

    print("CV Data Completeness Test")
    print("="*60)
    print(f"Data directory: {data_dir}")
    print(f"Output directory: {output_dir}")

    results = {}
    for variant in variants:
        results[variant] = test_variant(variant, data_dir, output_dir)

    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)

    all_passed = all(results.values())
    for variant, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{variant:25} {status}")

    print("="*60)

    if all_passed:
        print("🎉 All variants passed!")
        return 0
    else:
        print("⚠️  Some variants have issues")
        return 1

if __name__ == '__main__':
    sys.exit(main())
