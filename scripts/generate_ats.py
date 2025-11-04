#!/usr/bin/env python3
"""
ATS-Friendly CV Generator
Generates plain text CVs optimized for Applicant Tracking Systems.

ATS systems parse text-based content and look for keywords. This generator:
- Uses simple, parseable format
- Includes all keywords prominently
- Avoids complex formatting that confuses parsers
- Structures data in a way ATS systems expect
"""

import yaml
import argparse
from pathlib import Path
from typing import Dict, Any, List

def load_yaml_data(data_dir: Path) -> Dict[str, Any]:
    """Load all YAML files."""
    data = {}
    required_files = ['personal', 'experience', 'skills', 'strengths', 'education', 'certifications']

    for yaml_file in data_dir.glob('*.yaml'):
        with open(yaml_file) as f:
            data[yaml_file.stem] = yaml.safe_load(f)

    missing = [f for f in required_files if f not in data]
    if missing:
        raise ValueError(f"Missing required YAML files: {', '.join(missing)}.yaml")

    return data

def generate_header(personal: Dict[str, Any], tagline_key: str) -> str:
    """Generate header section with contact info."""
    lines = []

    # Name - centered, all caps for ATS visibility
    name = f"{personal['first_name']} {personal['last_name']}".upper()
    lines.append(name)
    lines.append(personal['taglines'][tagline_key])
    lines.append("")

    # Contact info - one item per line for ATS parsing
    lines.append("CONTACT INFORMATION")
    lines.append("-" * 50)
    lines.append(f"Email: {personal['email']}")
    lines.append(f"Phone: {personal['phone']}")
    lines.append(f"Location: {personal['location']}")
    lines.append(f"LinkedIn: {personal['linkedin']}")
    lines.append(f"GitHub: {personal['github']}")
    lines.append(f"Website: {personal['website']}")
    lines.append("")

    return "\n".join(lines)

def generate_summary(strengths: List[Dict[str, Any]], role_tags: List[str]) -> str:
    """Generate professional summary optimized for ATS keywords."""
    lines = []
    lines.append("PROFESSIONAL SUMMARY")
    lines.append("-" * 50)

    # Use the first matching strength's description
    relevant_strengths = [s for s in strengths if any(tag in s.get('tags', []) for tag in role_tags)]
    if relevant_strengths:
        lines.append(relevant_strengths[0]['description'])
    elif strengths:
        lines.append(strengths[0]['description'])

    lines.append("")
    return "\n".join(lines)

def generate_skills(skills: Dict[str, List[str]]) -> str:
    """Generate skills section with clear categorization for ATS."""
    lines = []
    lines.append("TECHNICAL SKILLS")
    lines.append("-" * 50)

    for category, items in skills.items():
        lines.append(f"\n{category}:")
        # List all skills on separate lines OR comma-separated
        # Different ATS systems prefer different formats, so we use both:
        skills_line = ", ".join(items)
        lines.append(skills_line)

    lines.append("")
    return "\n".join(lines)

def generate_experience(experience: List[Dict[str, Any]], role_tags: List[str]) -> str:
    """Generate experience section."""
    lines = []
    lines.append("PROFESSIONAL EXPERIENCE")
    lines.append("-" * 50)

    # Filter experience by tags
    relevant_exp = [e for e in experience if any(tag in e.get('tags', []) for tag in role_tags)]
    if not relevant_exp:
        relevant_exp = experience  # Fall back to all experience

    for job in relevant_exp:
        lines.append("")
        lines.append(f"{job['title']}")
        lines.append(f"{job['company']} | {job['location']}")
        lines.append(f"{job['start_date']} - {job['end_date']}")
        lines.append("")

        for achievement in job['achievements']:
            lines.append(f"• {achievement}")

    lines.append("")
    return "\n".join(lines)

def generate_education(education: List[Dict[str, Any]]) -> str:
    """Generate education section."""
    lines = []
    lines.append("EDUCATION")
    lines.append("-" * 50)

    for edu in education:
        lines.append("")
        lines.append(edu['degree'])
        if edu.get('specialization'):
            lines.append(f"Specialization: {edu['specialization']}")
        lines.append(f"{edu['institution']} | {edu['location']}")
        lines.append(f"{edu['start_date']} - {edu['end_date']}")

    lines.append("")
    return "\n".join(lines)

def generate_certifications(certifications: List[Dict[str, Any]], role_tags: List[str]) -> str:
    """Generate certifications section."""
    lines = []
    lines.append("CERTIFICATIONS")
    lines.append("-" * 50)

    # Filter certifications by tags
    relevant_certs = [c for c in certifications if any(tag in c.get('tags', []) for tag in role_tags)]
    if not relevant_certs:
        relevant_certs = certifications[:5]  # Limit to top 5 if no filtering

    for cert in relevant_certs:
        lines.append(f"• {cert['name']}")
        if cert.get('issuer'):
            lines.append(f"  Issued by: {cert['issuer']}")
        if cert.get('date'):
            lines.append(f"  Date: {cert['date']}")

    lines.append("")
    return "\n".join(lines)

def generate_ats_cv(data: Dict[str, Any], variant: str) -> str:
    """Generate complete ATS-friendly CV."""

    # Map variants to tagline keys and role tags
    variant_config = {
        'software-developer': {
            'tagline_key': 'software-developer',
            'role_tags': ['development', 'technical']
        },
        'devops-engineer': {
            'tagline_key': 'devops-engineer',
            'role_tags': ['devops', 'automation']
        },
        'cloud-engineer': {
            'tagline_key': 'cloud-engineer',
            'role_tags': ['cloud', 'infrastructure']
        }
    }

    config = variant_config[variant]

    # Build CV sections
    sections = []
    sections.append(generate_header(data['personal'], config['tagline_key']))
    sections.append(generate_summary(data['strengths'], config['role_tags']))
    sections.append(generate_skills(data['skills']))
    sections.append(generate_experience(data['experience'], config['role_tags']))
    sections.append(generate_education(data['education']))

    if data['certifications']:
        sections.append(generate_certifications(data['certifications'], config['role_tags']))

    # Add footer note
    sections.append("")
    sections.append("-" * 50)
    sections.append("This is an ATS-optimized version of my CV.")
    sections.append("For a formatted PDF version, please visit my website or LinkedIn profile.")
    sections.append("")

    return "\n".join(sections)

def main():
    parser = argparse.ArgumentParser(
        description='ATS-Friendly CV Generator',
        epilog='Generates plain text CVs optimized for Applicant Tracking Systems'
    )
    parser.add_argument('--variant', required=True,
                       choices=['software-developer', 'devops-engineer', 'cloud-engineer'],
                       help='CV variant to generate')
    parser.add_argument('--data-dir', required=True, type=Path,
                       help='Directory containing YAML data files')
    parser.add_argument('--output', required=True, type=Path,
                       help='Output .txt file path')
    args = parser.parse_args()

    try:
        # Load data
        print(f"Loading YAML data from {args.data_dir}...")
        data = load_yaml_data(args.data_dir)

        # Generate ATS CV
        print(f"Generating ATS-friendly CV for variant: {args.variant}")
        cv_text = generate_ats_cv(data, args.variant)

        # Write output
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(cv_text)

        lines = cv_text.count('\n')
        size = len(cv_text.encode('utf-8'))
        print(f"✓ Generated {args.output}")
        print(f"  Lines: {lines}")
        print(f"  Size: {size} bytes")
        print(f"\nATS Optimization Tips:")
        print("  • Use this version when applying through online forms")
        print("  • Copy/paste into text fields or upload as .txt")
        print("  • All keywords are included for ATS parsing")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
