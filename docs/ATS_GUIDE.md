# ATS (Applicant Tracking System) Optimization Guide

> **75% of CVs never reach a human recruiter** - they're filtered out by ATS software first.

This guide helps you understand ATS systems and optimize your CV to get past them.

## What is an ATS?

An **Applicant Tracking System (ATS)** is software that:
- Scans and parses your CV
- Extracts key information (skills, experience, education)
- Scores candidates based on keyword matches
- Filters out candidates before human review

**Companies using ATS:** 98% of Fortune 500 companies, and most companies with 50+ employees.

## Why This Template Includes ATS-Friendly Versions

Our template generates **two types of CVs**:

1. **PDF (LaTeX)** - Beautiful, professionally designed
   - Use for: Networking, direct emails, portfolios, in-person meetings
   - When to use: After you've passed ATS screening or when applying directly to a person

2. **Plain Text (ATS-optimized)** - Simple, keyword-rich
   - Use for: Online application forms, company career portals
   - When to use: Applying through company websites or job boards

## How ATS Systems Work

### 1. Parsing
ATS attempts to read your CV and extract:
- Contact information
- Work experience (dates, titles, companies)
- Education
- Skills
- Certifications

**Problem:** Complex formatting, tables, columns, and graphics confuse parsers.

**Solution:** Our plain text version uses simple, linear format that any ATS can read.

### 2. Keyword Matching
ATS searches for specific keywords from the job description:
- Technical skills (Python, AWS, React, etc.)
- Soft skills (leadership, collaboration)
- Certifications (AWS Certified, Kubernetes, etc.)
- Industry terms (CI/CD, microservices, agile)

**Problem:** If your CV doesn't contain these keywords, you're filtered out.

**Solution:** Our template ensures all your skills and technologies are clearly listed.

### 3. Scoring
ATS assigns scores based on:
- Keyword frequency and relevance
- Years of experience
- Education level
- Proper formatting and structure

**Problem:** Even qualified candidates get low scores if CV isn't optimized.

**Solution:** Our format maximizes keyword visibility while maintaining readability.

## ATS Optimization Checklist

### ✅ Do's

**Formatting:**
- [x] Use standard section headings (EXPERIENCE, EDUCATION, SKILLS)
- [x] Use simple formatting (no tables, text boxes, headers/footers)
- [x] Use standard fonts (Arial, Calibri, Times New Roman)
- [x] Left-align all text
- [x] Use plain bullet points (•, -, *)
- [x] Save as .docx or .txt (not .pdf unless specified)

**Content:**
- [x] Include keywords from job description naturally
- [x] Spell out acronyms first time: "CI/CD (Continuous Integration/Continuous Deployment)"
- [x] List all relevant skills, even if obvious
- [x] Use standard job titles (not creative variations)
- [x] Include full dates: "January 2020" not "Jan '20"
- [x] Add certifications with full names

**Keywords:**
- [x] Mirror job description language
- [x] Include variations (e.g., "JavaScript" and "JS")
- [x] Add skills in dedicated SKILLS section
- [x] Mention tools and technologies multiple times naturally

### ❌ Don'ts

**Formatting:**
- [ ] ~~Tables or columns~~ (ATS often can't parse them)
- [ ] ~~Images, graphics, or charts~~ (ATS can't read images)
- [ ] ~~Text boxes or shapes~~ (content may be skipped)
- [ ] ~~Headers and footers~~ (often ignored by ATS)
- [ ] ~~Unusual fonts or formatting~~ (may not render correctly)
- [ ] ~~Colors or highlighting~~ (lost when ATS extracts text)

**Content:**
- [ ] ~~Keyword stuffing~~ (ATS detects this, penalizes you)
- [ ] ~~Creative job titles~~ ("Code Ninja" instead of "Software Developer")
- [ ] ~~Only acronyms~~ (use "Amazon Web Services (AWS)" not just "AWS")
- [ ] ~~Pronouns~~ (I, me, my, we)
- [ ] ~~Typos or misspellings~~ (ATS is literal, won't match misspelled keywords)

## Using This Template for ATS Success

### Step 1: Generate Both Versions

```bash
# Generate beautiful PDF
make all

# Generate ATS-friendly text versions
python3 scripts/generate_ats.py --variant software-developer --data-dir data/ --output output/ats/software-developer.txt
python3 scripts/generate_ats.py --variant devops-engineer --data-dir data/ --output output/ats/devops-engineer.txt
python3 scripts/generate_ats.py --variant cloud-engineer --data-dir data/ --output output/ats/cloud-engineer.txt
```

### Step 2: Tailor for Each Job

Before applying, customize your ATS version:

1. **Extract keywords from job description:**
   - Required skills
   - Preferred qualifications
   - Tools and technologies
   - Industry terms

2. **Update your YAML data to include these keywords:**
   ```yaml
   # data/skills.yaml
   Programming Languages:
     - "Python"  # If job mentions Python
     - "JavaScript"  # If job mentions JavaScript
   ```

3. **Regenerate your CV:**
   ```bash
   python3 scripts/generate_ats.py --variant software-developer --data-dir data/ --output output/ats/software-developer.txt
   ```

### Step 3: Test Your ATS CV

**Free ATS testing tools:**
- [Jobscan](https://www.jobscan.co/) - Compare your CV to job description
- [Resume Worded](https://resumeworded.com/) - ATS compatibility check
- [VMock](https://www.vmock.com/) - AI-powered CV analysis

**Manual test:**
1. Copy your CV text
2. Paste into plain text editor (Notepad, TextEdit)
3. Can you easily read and understand it? If yes, so can ATS.

### Step 4: Submit Strategically

**When applying online:**
1. Use ATS-friendly .txt or .docx version
2. Copy/paste into text fields (don't rely on upload parsing)
3. Manually enter all information in forms (even if redundant)
4. Include PDF version as "additional document" if allowed

**When emailing directly:**
1. Use beautiful PDF version
2. Mention in email you have ATS-friendly version if needed

## Common ATS Mistakes by Junior Developers

### Mistake 1: Using Only PDF

**Problem:** Many companies only accept .docx or .txt for ATS compatibility.

**Solution:** Always have .txt version ready. Our template generates this automatically.

### Mistake 2: Missing Keywords

**Problem:** CV says "worked with containers" but job says "Docker" and "Kubernetes" specifically.

**Solution:** Be explicit. List specific technologies by name.

❌ "Experience with containerization technologies"
✅ "Experience with Docker and Kubernetes for container orchestration"

### Mistake 3: Creative Formatting

**Problem:** Two-column CV looks great but ATS reads it left-to-right, mixing sections.

**Solution:** Use single-column, linear format for ATS version (our .txt format).

### Mistake 4: Acronym-Only

**Problem:** CV says "CI/CD" but ATS searches for "Continuous Integration"

**Solution:** Use both:
- First mention: "CI/CD (Continuous Integration/Continuous Deployment)"
- Later mentions: "CI/CD"

### Mistake 5: Wrong File Format

**Problem:** Submitting .pages or .odt files that ATS can't read.

**Solution:** Stick to .docx, .txt, or .pdf (if specified).

## ATS-Friendly Keywords by Role

### Software Developer
```
Core: Programming, Software Development, Full-Stack, Frontend, Backend
Languages: Python, JavaScript, TypeScript, Java, Go, React, Node.js
Practices: Agile, Scrum, Test-Driven Development (TDD), Code Review
Tools: Git, GitHub, GitLab, JIRA, VS Code
Testing: Unit Testing, Integration Testing, Jest, PyTest
```

### DevOps Engineer
```
Core: DevOps, CI/CD, Infrastructure as Code (IaC), Site Reliability Engineering (SRE)
Tools: Jenkins, GitHub Actions, GitLab CI, ArgoCD, Terraform, Ansible
Containers: Docker, Kubernetes, Container Orchestration, Helm
Cloud: AWS, Azure, GCP, Cloud Infrastructure
Monitoring: Prometheus, Grafana, ELK Stack, DataDog
```

### Cloud Engineer
```
Core: Cloud Architecture, Cloud Infrastructure, Cloud Migration, Multi-Cloud
AWS: EC2, S3, Lambda, VPC, CloudFormation, EKS
Azure: Virtual Machines, Azure DevOps, AKS, ARM Templates
GCP: Compute Engine, Cloud Functions, GKE, Cloud Deployment Manager
IaC: Terraform, Pulumi, CloudFormation, ARM Templates
Concepts: High Availability, Disaster Recovery, Cost Optimization, Scalability
```

## FAQ

**Q: Should I only use the ATS version?**
A: No! Use ATS version for online applications, PDF version for everything else. The PDF looks much better.

**Q: Can I submit the beautiful PDF to online portals?**
A: Only if the job posting says "PDF preferred" or "PDF accepted". Otherwise, use .txt or .docx.

**Q: How do I know if a company uses ATS?**
A: Assume they do if:
- Applying through online portal
- Company has 50+ employees
- Job is posted on major job board

**Q: Should I stuff keywords to beat ATS?**
A: No. Include relevant keywords naturally. ATS systems detect keyword stuffing and modern ones penalize it.

**Q: Does ATS reject CVs automatically?**
A: Yes and no. ATS ranks candidates. Hiring managers typically review top 25-50 ranked CVs. Lower scores = less likely to be reviewed.

**Q: Can I use color in ATS CV?**
A: For .txt version, no. For .docx version, minimal color is okay, but focus on content over design.

## Resources

- [Jobscan ATS Blog](https://www.jobscan.co/blog/) - Latest ATS trends and tips
- [Indeed Career Guide: ATS](https://www.indeed.com/career-advice/resumes-cover-letters/ats-resume) - ATS optimization basics
- [Harvard Extension: ATS Formatting](https://careerservices.extension.harvard.edu/guides/ats-formatting/) - Detailed ATS guide

## Remember

**ATS is a gatekeeper, not a judge.**

Your goal is to:
1. Get past the ATS filter (using optimized format and keywords)
2. Impress the human reviewer (using compelling content and achievements)

This template helps with both. Use the right version at the right time:
- **ATS version**: Get past the robots
- **PDF version**: Impress the humans

Good luck! 🎯
