# CV Pipeline Template

> **Click "Use this template" to create your own CV pipeline!**

Automated CV generation pipeline that creates multiple psychologically-optimized CV variants from YAML data.

## Quick Start

### 1. Use This Template

Click the green "Use this template" button above to create your own repository.

### 2. Edit Your Data

Update the YAML files in `data/` with your information:

```bash
# Edit your personal info
vim data/personal.yaml

# Edit your work experience
vim data/experience.yaml

# Edit skills, education, certifications, strengths
vim data/skills.yaml data/education.yaml data/certifications.yaml data/strengths.yaml
```

### 3. Push to GitHub

```bash
git add .
git commit -m "Add my CV data"
git push
```

### 4. Get Your CVs

GitHub Actions will automatically:
- Generate 3 CV variants
- Run tests to verify all data is included
- Create a release with PDF downloads

Download from: `https://github.com/YOUR_USERNAME/YOUR_REPO/releases/latest`

## What You Get

**Three psychologically-optimized CV variants**:
- **Software Developer** - Creativity, problem-solving, technical expertise (Purple - innovation)
- **DevOps Engineer** - Reliability, automation, efficiency (Green - stability)
- **Cloud Engineer** - Trust, scalability, expertise (Blue - professionalism)

Each variant filters your experience based on tags and uses color psychology to create the right first impression

## Data Structure

### personal.yaml
Basic contact information and taglines for each variant:

```yaml
first_name: "John"
last_name: "Doe"
email: "john.doe@example.com"
linkedin: "https://linkedin.com/in/johndoe"
github: "https://github.com/johndoe"
taglines:
  engineering-manager: "Engineering Manager"
  developer-advocate: "Developer Advocate"
  platform-engineer: "Senior Platform Engineer"
```

### experience.yaml
Work experience with tags for filtering:

```yaml
- title: "Senior Platform Engineer"
  company: "Tech Corp Inc"
  location: "Remote"
  start_date: "01/2022"
  end_date: "present"
  tags: ["technical", "platform", "leadership"]  # Used for filtering!
  achievements:
    - "Led development of microservices architecture"
    - "Improved deployment efficiency by 60%"
```

**Tag guide**:
- `development` - Appears in Software Developer CV
- `devops` - Appears in DevOps Engineer CV
- `cloud` - Appears in Cloud Engineer CV
- Mix tags to appear in multiple variants

### Other files
- `skills.yaml` - Programming languages, tools, cloud platforms
- `education.yaml` - Degrees and institutions
- `certifications.yaml` - Professional certifications with tags
- `strengths.yaml` - Key strengths with descriptions and tags

## Customization

### Add New Variants

1. Create template directory: `templates/new-variant/`
2. Add template file: `templates/new-variant/template.tex.j2`
3. Add tagline to `data/personal.yaml`
4. Tag relevant experience in `data/experience.yaml`
5. Update `Makefile` VARIANTS list
6. Update `.github/workflows/cv-build.yml` matrix

### Modify Colors/Design

Edit templates in `templates/*/template.tex.j2` - each uses AltaCV LaTeX class with customizable colors.

**Current color schemes** (based on color psychology research):
- **Software Developer**: Purple (#7C3AED) - Innovation, creativity, problem-solving
- **DevOps Engineer**: Green (#059669) - Growth, stability, operational health
- **Cloud Engineer**: Steel Blue (#4682B4) - Trust, reliability, professionalism

## Testing Locally

```bash
# Install dependencies
pip install Jinja2 PyYAML

# Build all CVs
make all

# Run tests
make test

# View PDFs
ls output/generated/*.pdf
```

## Requirements

- Python 3.11+
- TeX Live (pdflatex)
- poppler-utils (pdftotext, pdfinfo)

## How It Works

1. **YAML → Python**: `scripts/generate.py` reads YAML data files
2. **Jinja2 Templates**: Populates LaTeX templates with filtered data
3. **LaTeX → PDF**: Compiles templates into professional PDFs
4. **Testing**: `scripts/test_data_completeness.py` verifies all data appears
5. **CI/CD**: GitHub Actions automates the entire pipeline

## Troubleshooting

### PDFs not generating locally?

Check dependencies:
```bash
# Python packages
pip list | grep -E "Jinja2|PyYAML"

# LaTeX
pdflatex --version

# PDF utilities
pdftotext -v
```

### Tests failing?

Run verbose test output:
```bash
python scripts/test_data_completeness.py
```

Common issues:
- Missing data in YAML files
- Special characters in LaTeX (use `\&` for `&`, `\%` for `%`)
- Tags not matching template filters

### GitHub Actions failing?

Check:
1. YAML syntax is valid
2. No special characters breaking LaTeX compilation
3. All required files present in repository

## Color Psychology Research

The color schemes for each CV variant are based on research in color psychology and professional perception:

**Research Sources:**
- [Resume Color Psychology - Standout CV](https://standout-cv.com/usa/resume-advice/resume-color-psychology) - How colors influence hiring manager perception
- [Color Psychology in Resume Design](https://www.stopthebleedday.org/2024/02/14/color-psychology-in-resume-design-using-color-to-influence-perception/) - Color impact on first impressions
- [Colors on Your Resume - Resume Giants](https://www.resumegiants.com/blog/colors-on-resume/) - Professional color choices and their meanings

**Key Findings:**
- **Purple (#7C3AED)**: Associated with creativity, innovation, and problem-solving - ideal for Software Developers
- **Green (#059669)**: Conveys stability, growth, and operational health - perfect for DevOps Engineers
- **Blue (#4682B4)**: Represents trust, reliability, and professionalism - suited for Cloud Engineers

## License

MIT - Use this template freely for your own CV!

## FAQ

**Q: Can I add more CV variants?**
A: Yes! Create a new template directory, add Jinja2 template, and update the Makefile.

**Q: Do I need to configure secrets or tokens?**
A: No! The template works out-of-the-box with no configuration needed.

**Q: Can I customize the LaTeX templates?**
A: Absolutely! Edit the `.tex.j2` files in `templates/*/` directories.

**Q: How do I change which experience appears in each variant?**
A: Use the `tags` field in `experience.yaml`. Each template filters based on specific tags.

**Q: Can I use this for commercial purposes?**
A: Yes! This template is MIT licensed - use it however you'd like.
