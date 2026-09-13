#!/usr/bin/env python3
"""
Simple CV generator - No templating, just direct YAML to LaTeX generation.

All variants share ONE fixed two-page, two-column layout (see render_cv):
  page 1 = the pitch  -> left: Profile + role-tailored Highlights
                         right: Key Strengths + sidebar extras + Languages
  page 2 = the detail -> left: Professional Experience
                         right: Expertise + tech tags + Education + Certifications

Only CONTENT differs per variant. Each generate_* function builds a `spec`
dict (palette, fonts, profile text, highlights, strengths, tags) and hands it
to render_cv. The layout itself lives in render_cv and the _section helpers.
"""

import sys
import yaml
import argparse
from pathlib import Path
from typing import Dict, Any, List

def escape_latex(text: str) -> str:
    """Escape LaTeX special characters."""
    if not isinstance(text, str):
        text = str(text)
    chars = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }
    return ''.join(chars.get(c, c) for c in text)

def load_yaml_data(data_dir: Path) -> Dict[str, Any]:
    """Load all YAML files with validation."""
    data = {}
    required_files = ['personal', 'experience', 'skills', 'strengths', 'education']

    for yaml_file in data_dir.glob('*.yaml'):
        with open(yaml_file) as f:
            data[yaml_file.stem] = yaml.safe_load(f)

    data['certifications'] = data.get('certifications') or []

    # Validate all required files are present
    missing = [f for f in required_files if f not in data]
    if missing:
        raise ValueError(f"Missing required YAML files: {', '.join(missing)}.yaml")

    # Validate required fields in personal.yaml
    personal = data['personal']
    required_personal = ['first_name', 'last_name', 'email', 'phone', 'location', 'website', 'linkedin', 'github', 'taglines']
    missing_personal = [f for f in required_personal if f not in personal]
    if missing_personal:
        raise ValueError(f"Missing required fields in personal.yaml: {', '.join(missing_personal)}")

    # Validate taglines exist for all variants
    required_taglines = list(SPEC_BUILDERS)
    missing_taglines = [t for t in required_taglines if t not in personal['taglines']]
    if missing_taglines:
        raise ValueError(f"Missing taglines in personal.yaml: {', '.join(missing_taglines)}")

    return data


# ---------------------------------------------------------------------------
# Shared layout: preamble, fonts, palettes, section helpers, renderer.
# Everything below render_cv is variant-agnostic structure; the generate_*
# functions only assemble per-variant CONTENT into a spec.
# ---------------------------------------------------------------------------

# Preamble shared by every variant. %%FONTS%% and %%STYLE%% are swapped in per
# variant (font family + colour palette). The two-page layout relies on the
# emergencystretch/hyphenpenalty tuning (clean justified right edge in narrow
# columns) and the \cvevent override (date + location on one line) below.
_PREAMBLE_TEMPLATE = r'''\documentclass[10pt,a4paper,withhyper]{altacv}

\geometry{left=1cm,right=1cm,top=1.5cm,bottom=1.5cm,columnsep=1.2cm}

\usepackage{paracol}

%%FONTS%%

%%STYLE%%

\renewcommand{\cvItemMarker}{{\small\textbullet}}
\renewcommand{\cvRatingMarker}{\faCircle}

% Override linkedin to show "LinkedIn" text with clickable link
\renewcommand{\linkedin}[1]{%
  \printinfo{\faLinkedin}{LinkedIn}[https://linkedin.com/in/#1]%
}

\begin{document}

% Body text is justified by default; emergencystretch + easier hyphenation give a clean,
% consistent right edge in the narrow two-column layout instead of short, ragged lines.
\setlength{\emergencystretch}{3em}
\hyphenpenalty=50

% Keep date and location on one line so the location marker sits beside the dates, instead of
% altacv's default two half-width boxes that strand the location mid-column.
\renewcommand{\cvevent}[4]{%
  {\large\color{emphasis}#1\par}%
  \smallskip\normalsize
  \ifstrequal{#2}{}{}{\textbf{\color{accent}#2}\par\smallskip}%
  \ifstrequal{#3}{}{}{{\small\cvDateMarker~#3}}%
  \ifstrequal{#4}{}{}{{\small\quad\cvLocationMarker~#4}}\par%
  \medskip\normalsize
}
'''

# --- Font blocks (\iftutex ... \fi) -----------------------------------------

_FONTS_ROBOTO_SLAB = r'''\iftutex
  \setmainfont{Roboto Slab}
  \setsansfont{Lato}
  \renewcommand{\familydefault}{\sfdefault}
\else
  \usepackage[rm]{roboto}
  \usepackage[defaultsans]{lato}
  \renewcommand{\familydefault}{\sfdefault}
\fi'''

_FONTS_LATO = r'''\iftutex
  \setmainfont{Lato}
  \setsansfont{Lato}
  \renewcommand{\familydefault}{\sfdefault}
\else
  \usepackage[defaultsans]{lato}
  \renewcommand{\familydefault}{\sfdefault}
\fi'''

_FONTS_ROBOTO = r'''\iftutex
  \setmainfont{Roboto}
  \setsansfont{Roboto}
  \setmonofont{Roboto Mono}
  \renewcommand{\familydefault}{\sfdefault}
\else
  \usepackage{roboto}
  \usepackage[T1]{fontenc}
  \renewcommand{\familydefault}{\sfdefault}
\fi'''

# --- Colour + heading-font palettes (one per variant) -----------------------

_STYLE_SOFTWARE_DEVELOPER = r'''% SOFTWARE DEVELOPER: Creativity & Problem-Solving (purple)
\definecolor{SlateGrey}{HTML}{2E2E2E}
\definecolor{LightGrey}{HTML}{666666}
\definecolor{InnovationPurple}{HTML}{7c3aed}
\definecolor{DeepPurple}{HTML}{4c1d95}
\definecolor{AccentTeal}{HTML}{0d9488}
\colorlet{name}{DeepPurple}
\colorlet{tagline}{InnovationPurple}
\colorlet{heading}{DeepPurple}
\colorlet{headingrule}{InnovationPurple}
\colorlet{subheading}{InnovationPurple}
\colorlet{accent}{AccentTeal}
\colorlet{emphasis}{SlateGrey}
\colorlet{body}{LightGrey}

\renewcommand{\namefont}{\Huge\rmfamily\bfseries}
\renewcommand{\personalinfofont}{\footnotesize}
\renewcommand{\cvsectionfont}{\LARGE\rmfamily\bfseries}
\renewcommand{\cvsubsectionfont}{\large\bfseries}'''

_STYLE_DEVOPS_ENGINEER = r'''% DEVOPS ENGINEER: Energy & Collaboration (orange)
\definecolor{SlateGrey}{HTML}{2E2E2E}
\definecolor{LightGrey}{HTML}{666666}
\definecolor{EnergeticOrange}{HTML}{ff6b35}
\definecolor{FriendlyTeal}{HTML}{00a3bf}
\definecolor{CommunityPurple}{HTML}{7c3aed}
\colorlet{name}{EnergeticOrange}
\colorlet{tagline}{CommunityPurple}
\colorlet{heading}{EnergeticOrange}
\colorlet{headingrule}{FriendlyTeal}
\colorlet{subheading}{CommunityPurple}
\colorlet{accent}{FriendlyTeal}
\colorlet{emphasis}{SlateGrey}
\colorlet{body}{LightGrey}

\renewcommand{\namefont}{\Huge\sffamily\bfseries}
\renewcommand{\personalinfofont}{\footnotesize}
\renewcommand{\cvsectionfont}{\LARGE\sffamily\bfseries}
\renewcommand{\cvsubsectionfont}{\large\bfseries}'''

_STYLE_CLOUD_ENGINEER = r'''% CLOUD ENGINEER: Trust & Reliability (steel blue)
\definecolor{SlateGrey}{HTML}{2E2E2E}
\definecolor{LightGrey}{HTML}{666666}
\definecolor{SteelBlue}{HTML}{4682b4}
\definecolor{IndustrialGrey}{HTML}{6c757d}
\definecolor{SystemGreen}{HTML}{059669}
\colorlet{name}{SlateGrey}
\colorlet{tagline}{SteelBlue}
\colorlet{heading}{SteelBlue}
\colorlet{headingrule}{IndustrialGrey}
\colorlet{subheading}{SteelBlue}
\colorlet{accent}{SystemGreen}
\colorlet{emphasis}{SlateGrey}
\colorlet{body}{LightGrey}

\renewcommand{\namefont}{\Huge\sffamily\bfseries}
\renewcommand{\personalinfofont}{\footnotesize}
\renewcommand{\cvsectionfont}{\LARGE\sffamily\bfseries}
\renewcommand{\cvsubsectionfont}{\large\bfseries}'''

def _win_highlights(data: Dict[str, Any], n: int,
                    tags: List[str] = None) -> List[str]:
    """Role-tailored highlight bullets for page 1.

    Source of truth is data/wins.yaml `cv_highlights` (short, attribution-checked
    lines; see its meta.attribution_flags before rephrasing any of them). When
    that file is absent the fallback is the first achievement of each job, optionally
    restricted to jobs carrying one of `tags`, so a fresh template still renders.
    """
    items = (data.get('wins') or {}).get('cv_highlights') or []
    if not items:
        for job in data.get('experience', []):
            if tags and not set(tags) & set(job.get('tags', [])):
                continue
            items.extend(job.get('achievements', [])[:2])
    return items[:n]


# --- Section helpers (each returns a LaTeX fragment) -------------------------

def _header(personal: Dict[str, Any], tagline_key: str, columnratio: str,
            include_phone: bool = True, include_youtube: bool = False,
            tagline_override: str = None) -> str:
    """Name, tagline, contact block, then open the page-1 paracol."""
    tagline = tagline_override if tagline_override else personal['taglines'][tagline_key]
    s = f"\\name{{{escape_latex(personal['first_name'])} {escape_latex(personal['last_name'])}}}\n"
    s += f"\\tagline{{{escape_latex(tagline)}}}\n\n"

    s += "\\personalinfo{%\n"
    s += f"  \\email{{{escape_latex(personal['email'])}}}\n"
    if include_phone:
        s += f"  \\phone{{{escape_latex(personal['phone'])}}}\n"
    s += f"  \\location{{{escape_latex(personal['location'])}}}\n"

    website = personal['website'].replace('https://', '').replace('http://', '')
    s += f"  \\homepage{{{escape_latex(website)}}}\n"

    linkedin_id = personal['linkedin'].replace('https://www.linkedin.com/in/', '').replace('https://linkedin.com/in/', '').replace('/', '')
    s += f"  \\linkedin{{{escape_latex(linkedin_id)}}}\n"

    github_user = personal['github'].replace('https://github.com/', '').replace('/', '')
    s += f"  \\github{{{escape_latex(github_user)}}}\n"

    if include_youtube and personal.get('youtube'):
        s += f"  \\printinfo{{\\faYoutube}}{{YouTube}}[{personal['youtube']}]\n"

    s += "}\n\n"
    s += "\\makecvheader\n\n"
    s += f"\\columnratio{{{columnratio}}}\n\n"
    s += "\\begin{paracol}{2}\n\n"
    return s


def _profile(title: str, paras: List[str]) -> str:
    """Profile section: short paragraphs with visible breaks (altacv has no parskip)."""
    s = f"\\cvsection{{{escape_latex(title)}}}\n\n"
    for j, para in enumerate(paras):
        s += f"{escape_latex(para)}\n\n"
        if j < len(paras) - 1:
            s += "\\smallskip\n\n"
    s += "\\medskip\n\n"
    return s


def _highlights(title: str, items: List[str]) -> str:
    """Role-tailored bulleted highlights box (page-1 left, below Profile)."""
    s = f"\\cvsection{{{escape_latex(title)}}}\n\n"
    s += "\\begin{itemize}\n"
    for it in items:
        s += f"\\item {escape_latex(it)}\n"
    s += "\\end{itemize}\n\n"
    s += "\\medskip\n\n"
    return s


def _strengths(title: str, strengths: List[Dict[str, Any]], marker: str) -> str:
    """Key Strengths as cvachievements (title + description), divided."""
    s = f"\\cvsection{{{escape_latex(title)}}}\n\n"
    for i, st in enumerate(strengths):
        s += f"\\cvachievement{{{marker}}}{{{escape_latex(st['title'])}}}{{{escape_latex(st['description'])}}}\n\n"
        if i < len(strengths) - 1:
            s += "\\divider\n\n"
    return s


def _text_section(title: str, text: str) -> str:
    """A short prose sidebar section (e.g. Industry Fit), spaced above."""
    return f"\\bigskip\n\n\\cvsection{{{escape_latex(title)}}}\n\n{escape_latex(text)}\n\n"


def _languages(skills: Dict[str, Any]) -> str:
    """Languages as tags in the page-1 sidebar."""
    if not skills.get('Languages'):
        return ''
    s = "\\bigskip\n\n\\cvsection{Languages}\n\n"
    for lang in skills['Languages']:
        s += f"\\cvtag{{{escape_latex(lang)}}}\n"
    s += "\n"
    return s


def _experience(title: str, jobs: List[Dict[str, Any]], ach_per_job: int) -> str:
    """Professional Experience (page-2 left)."""
    s = f"\\cvsection{{{escape_latex(title)}}}\n\n"
    for job in jobs:
        s += f"\\cvevent{{{escape_latex(job['title'])}}}{{{escape_latex(job['company'])}}}"
        s += f"{{{job['start_date']}--{job['end_date']}}}{{{escape_latex(job['location'])}}}\n"
        s += "\\begin{itemize}\n"
        for ach in job['achievements'][:ach_per_job]:
            s += f"\\item {escape_latex(ach)}\n"
        s += "\\end{itemize}\n\n"
        s += "\\divider\n\n"
    return s


def _tags(tags: List[str]) -> str:
    return ''.join(f"\\cvtag{{{escape_latex(t)}}}\n" for t in tags)


def _expertise_and_tech(spec: Dict[str, Any], skills: Dict[str, Any]) -> str:
    """Expertise tags + optional tech-tag groups + Technical Foundation (page-2 right)."""
    s = f"\\cvsection{{{escape_latex(spec['expertise_title'])}}}\n\n"
    s += _tags(spec['expertise_tags'])
    s += "\n\\divider\\smallskip\n\n"

    for label, tags in spec.get('tech_groups', []):
        s += f"\\textbf{{{escape_latex(label)}}}\n\n"
        s += _tags(tags)
        s += "\n\\divider\\smallskip\n\n"

    s += "\\textbf{Technical Foundation}\n\n"
    s += _tags(skills['Programming Languages'][:6])
    s += "\n"
    s += _tags(skills['DevOps and Cloud Technologies'][:8])
    s += "\n\\divider\\smallskip\n\n"
    return s


def _education(education: List[Dict[str, Any]]) -> str:
    s = "\\cvsection{Education}\n\n"
    for edu in education:
        degree = escape_latex(edu['degree'])
        if edu.get('specialization'):
            degree += f" ({escape_latex(edu['specialization'])})"
        s += f"\\cvevent{{{degree}}}{{{escape_latex(edu['institution'])}}}"
        s += f"{{{edu['start_date']}--{edu['end_date']}}}{{{escape_latex(edu['location'])}}}\n\n"
    return s


def _certifications(certifications: List[Dict[str, Any]], limit) -> str:
    certifications = certifications or []
    certs = certifications if limit is None else certifications[:limit]
    if not certs:
        return ''
    s = "\\cvsection{Certifications}\n\n"
    for cert in certs:
        s += f"\\cvtag{{{escape_latex(cert['name'])}}}\n"
    return s


def render_cv(data: Dict[str, Any], spec: Dict[str, Any]) -> str:
    """Assemble the shared two-page layout from a per-variant content spec."""
    personal = data['personal']
    skills = data['skills']
    education = data['education']
    certifications = data.get('certifications') or []
    strengths_all = data['strengths']
    experience_all = data['experience']

    latex = _PREAMBLE_TEMPLATE.replace('%%FONTS%%', spec['fonts']).replace('%%STYLE%%', spec['style'])
    latex += "\n"
    latex += _header(personal, spec['variant'], spec['columnratio'],
                     spec.get('include_phone', True), spec.get('include_youtube', False),
                     tagline_override=spec.get('tagline_override'))

    # ---- Page 1 (pitch) -------------------------------------------------
    # Left: Profile + role-tailored highlights.
    latex += _profile(spec['profile_title'], spec['profile_paras'])
    latex += _highlights(spec['highlights_title'], spec['highlights'])
    latex += "\\switchcolumn\n\n"

    # Right: Key Strengths + sidebar extras + Languages.
    sel_strengths = [strengths_all[i] for i in spec['strength_indices'] if i < len(strengths_all)]
    latex += _strengths(spec['strengths_title'], sel_strengths, spec.get('strength_marker', '\\faTrophy'))
    for title, text in spec.get('sidebar_extras', []):
        latex += _text_section(title, text)
    if spec.get('include_languages', True):
        latex += _languages(skills)

    latex += "\n\\end{paracol}\n\n\\newpage\n\n\\begin{paracol}{2}\n\n"

    # ---- Page 2 (detail) ------------------------------------------------
    # Left: full Professional Experience.
    jobs = experience_all[:spec['experience_count']]
    latex += _experience(spec['experience_title'], jobs, spec['achievements_per_job'])
    latex += "\\switchcolumn\n\n"

    # Right: Expertise + tech tags + Education + Certifications.
    latex += _expertise_and_tech(spec, skills)
    latex += _education(education)
    latex += _certifications(certifications, spec.get('cert_limit'))

    latex += "\n\\end{paracol}\n\n"
    latex += "\\end{document}\n"
    return latex


# ---------------------------------------------------------------------------
# Per-variant content specs. Layout is shared; only the content below changes.
# ---------------------------------------------------------------------------

def _spec_software_developer(data: Dict[str, Any]) -> Dict[str, Any]:
    """Software Developer: building products, problem-solving, code quality."""
    return {
        'variant': 'software-developer',
        'fonts': _FONTS_ROBOTO_SLAB,
        'style': _STYLE_SOFTWARE_DEVELOPER,
        'columnratio': '0.62',
        'profile_title': 'Profile',
        'profile_paras': [
            "Software developer who builds and ships production systems end to end, "
            "from API design and data modelling to the tests and automation that keep "
            "them reliable.",

            "I care about clean, maintainable code and about the people who use it: "
            "I write the documentation, review the pull requests, and stay close to the "
            "problem the software is meant to solve.",

            "Comfortable in agile teams and across the stack, and quick to pick up a new "
            "language or framework when the job calls for it.",
        ],
        'highlights_title': 'Highlights',
        'highlights': _win_highlights(data, 6, tags=['development']),
        'strengths_title': 'Key Strengths',
        'strength_indices': [0, 2, 4],
        'strength_marker': '\\faLightbulb',
        'include_languages': True,
        'experience_title': 'Professional Experience',
        'experience_count': 5,
        'achievements_per_job': 2,
        'expertise_title': 'Expertise',
        'expertise_tags': ["Backend Development", "API Design", "Testing & Quality",
                           "Problem Solving", "Agile Delivery"],
        'tech_groups': [],
        'cert_limit': None,
    }


def _spec_devops_engineer(data: Dict[str, Any]) -> Dict[str, Any]:
    """DevOps Engineer: automation, CI/CD, developer enablement."""
    skills = data['skills']
    tech_groups = []
    if 'Cloud Platforms' in skills:
        tech_groups.append(("Cloud Platforms", skills['Cloud Platforms']))
    return {
        'variant': 'devops-engineer',
        'fonts': _FONTS_LATO,
        'style': _STYLE_DEVOPS_ENGINEER,
        'columnratio': '0.6',
        'profile_title': 'Profile',
        'profile_paras': [
            "DevOps engineer who removes friction between writing code and running it: "
            "CI/CD pipelines, GitOps workflows, and infrastructure as code that teams "
            "can trust.",

            "I automate the repetitive work, make deployments boring, and measure the "
            "result in shorter lead times and fewer incidents.",

            "I work best embedded with developers, turning their pain points into "
            "tooling and documentation they actually use.",
        ],
        'highlights_title': 'Highlights',
        'highlights': _win_highlights(data, 6, tags=['devops']),
        'strengths_title': 'Key Strengths',
        'strength_indices': [1, 3, 2],
        'strength_marker': '\\faCogs',
        'include_languages': True,
        'experience_title': 'Professional Experience',
        'experience_count': 5,
        'achievements_per_job': 2,
        'expertise_title': 'Expertise',
        'expertise_tags': ["CI/CD", "GitOps", "Infrastructure as Code",
                           "Automation", "Developer Experience"],
        'tech_groups': tech_groups,
        'cert_limit': 5,
    }


def _spec_cloud_engineer(data: Dict[str, Any]) -> Dict[str, Any]:
    """Cloud Engineer: scalable architecture, reliability, cost."""
    skills = data['skills']
    tech_groups = []
    if 'Cloud Platforms' in skills:
        tech_groups.append(("Cloud Platforms", skills['Cloud Platforms']))
    return {
        'variant': 'cloud-engineer',
        'fonts': _FONTS_ROBOTO,
        'style': _STYLE_CLOUD_ENGINEER,
        'columnratio': '0.62',
        'profile_title': 'Profile',
        'profile_paras': [
            "Cloud engineer with production experience designing, migrating, and "
            "operating workloads on AWS, GCP, and Azure.",

            "I build infrastructure that scales and stays up: Kubernetes platforms, "
            "Terraform-managed environments, and the monitoring and alerting that "
            "catches problems before users do.",

            "I keep an eye on cost as well as uptime, and I document what I build so "
            "the next engineer can run it.",
        ],
        'highlights_title': 'Highlights',
        'highlights': _win_highlights(data, 6, tags=['cloud']),
        'strengths_title': 'Key Strengths',
        'strength_indices': [1, 2, 4],
        'strength_marker': '\\faCloud',
        'include_languages': True,
        'experience_title': 'Professional Experience',
        'experience_count': 5,
        'achievements_per_job': 2,
        'expertise_title': 'Expertise',
        'expertise_tags': ["Cloud Architecture", "Kubernetes", "Reliability",
                           "Cost Optimization", "Migration"],
        'tech_groups': tech_groups,
        'cert_limit': None,
    }


# Registry of variant spec builders. Used by the CLI here AND by the
# per-application overlay system (scripts/application.py), which takes a base
# variant's spec and merges per-application overrides on top before rendering.
# To add a variant: write a _spec_<name>() builder, register it here, add its
# tagline to data/personal.yaml, and add it to the Makefile VARIANTS list.
SPEC_BUILDERS = {
    'software-developer': _spec_software_developer,
    'devops-engineer': _spec_devops_engineer,
    'cloud-engineer': _spec_cloud_engineer,
}

# Named palettes + font blocks, so an application overlay can borrow a different
# variant's look by name (style: cloud-engineer, fonts: lato) instead of pasting
# raw LaTeX.
STYLE_BY_NAME = {
    'software-developer': _STYLE_SOFTWARE_DEVELOPER,
    'devops-engineer': _STYLE_DEVOPS_ENGINEER,
    'cloud-engineer': _STYLE_CLOUD_ENGINEER,
}
FONTS_BY_NAME = {
    'roboto-slab': _FONTS_ROBOTO_SLAB,
    'lato': _FONTS_LATO,
    'roboto': _FONTS_ROBOTO,
}


def build_spec(variant: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Return the base content spec for a variant (no per-application overrides)."""
    return SPEC_BUILDERS[variant](data)


def generate(variant: str, data: Dict[str, Any]) -> str:
    """Render a base variant CV to LaTeX (no per-application overrides)."""
    return render_cv(data, build_spec(variant, data))


def main():
    parser = argparse.ArgumentParser(
        description='CV Generator - Direct YAML to LaTeX conversion',
        epilog='Generates LaTeX CV from YAML data with built-in validation'
    )
    parser.add_argument('--variant', required=True,
                       choices=sorted(SPEC_BUILDERS),
                       help='CV variant to generate')
    parser.add_argument('--data-dir', required=True, type=Path,
                       help='Directory containing YAML data files')
    parser.add_argument('--output', required=True, type=Path,
                       help='Output .tex file path')
    args = parser.parse_args()

    try:
        # Validate data directory exists
        if not args.data_dir.exists():
            print(f"Error: Data directory not found: {args.data_dir}", file=sys.stderr)
            return 1

        # Load and validate data
        print(f"Loading YAML data from {args.data_dir}...")
        data = load_yaml_data(args.data_dir)
        print(f"Loaded data files: {', '.join(sorted(data.keys()))}")

        print(f"Generating LaTeX for variant: {args.variant}")
        latex_output = generate(args.variant, data)

        # Validate output is not empty
        if not latex_output.strip():
            print("Error: Generated empty LaTeX output", file=sys.stderr)
            return 1

        # Validate LaTeX structure
        if '\\begin{document}' not in latex_output or '\\end{document}' not in latex_output:
            print("Error: Invalid LaTeX structure - missing document markers", file=sys.stderr)
            return 1

        # Write output
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(latex_output)

        lines = latex_output.count('\n')
        size = len(latex_output.encode('utf-8'))
        print(f"✓ Generated {args.output}")
        print(f"  Lines: {lines}")
        print(f"  Size: {size} bytes")

        return 0

    except ValueError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
