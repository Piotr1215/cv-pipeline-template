.PHONY: all clean help test test-substrate software-developer devops-engineer cloud-engineer ats-all jobs jobs-notify jobs-list jobs-tui applications applications-status open open-app setup

VARIANTS = software-developer devops-engineer cloud-engineer
DATA_DIR = data
TEMPLATE_DIR = templates
OUTPUT_DIR = output/generated
# Use the project virtualenv if present (run `make setup` once), else system python3.
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
VENV ?= .venv
TEXLIVE_IMAGE := ghcr.io/xu-cheng/texlive-debian:20261001@sha256:78ac2204b8df113aca0561e8f173ad5b89ee51e90795173d2fe9bcf0fbce162e

all: $(foreach v,$(VARIANTS),$(OUTPUT_DIR)/$(v).pdf) test

# Create the project virtualenv and install Python deps (textual TUI, requests, etc.)
setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "✓ venv ready (.venv). Run: make jobs-tui"

help:
	@echo "CV Pipeline Build System"
	@echo ""
	@echo "Setup:"
	@echo "  setup                - Create .venv and install Python deps (needed for jobs-tui)"
	@echo ""
	@echo "CV targets:"
	@echo "  all                  - Build all CV variants and run tests"
	@echo "  software-developer   - Build Software Developer CV"
	@echo "  devops-engineer      - Build DevOps Engineer CV"
	@echo "  cloud-engineer       - Build Cloud Engineer CV"
	@echo "  ats-all              - Generate all ATS-friendly text versions"
	@echo "  test                 - Verify all YAML data is rendered in PDFs"
	@echo "  clean                - Remove all generated files"
	@echo ""
	@echo "Job aggregator:"
	@echo "  jobs                 - Fetch and score jobs (no notifications)"
	@echo "  jobs-notify          - Fetch, score, and send ntfy notifications"
	@echo "  jobs-list            - List top matches for the first profile in data/goals.yaml"
	@echo "  jobs-tui             - Interactive job tracker TUI"
	@echo ""
	@echo "Applications (per-posting tailored CVs):"
	@echo "  applications         - Build every applications/<slug>/cv.pdf"
	@echo "  applications-status  - Print the application pipeline board"
	@echo "  (per app: python3 -m scripts.application {new|build|tailor|set-status} <slug>)"
	@echo ""
	@echo "Open a PDF:"
	@echo "  open                 - Open a variant PDF (fzf picker)"
	@echo "  open VIEW=cloud-engineer  - Open a specific variant"
	@echo "  open-app SLUG=<slug> - Open an application's tailored cv.pdf"

# Generate .tex from YAML - direct conversion, no templates
$(OUTPUT_DIR)/%.tex: $(DATA_DIR)/*.yaml scripts/generate.py
	@echo "==> Generating $*.tex from YAML data..."
	@mkdir -p $(OUTPUT_DIR)
	$(PYTHON) scripts/generate.py \
		--variant $* \
		--data-dir $(DATA_DIR) \
		--output $@
	@echo ""

# Compile .tex to .pdf using pdflatex (Phase 1 contract)
$(OUTPUT_DIR)/%.pdf: $(OUTPUT_DIR)/%.tex
	@echo "==> Copying LaTeX class files..."
	@cp $(TEMPLATE_DIR)/altacv-class/*.cls $(OUTPUT_DIR)/ 2>/dev/null || true
	@cp $(TEMPLATE_DIR)/altacv-class/*.cfg $(OUTPUT_DIR)/ 2>/dev/null || true
	@echo "==> Compiling $*.tex to PDF..."
	@cd $(OUTPUT_DIR) && { pdflatex -interaction=nonstopmode -halt-on-error $*.tex || { sed -n '/^!/{p; :a; n; p; ba;}' $*.log | head -30; exit 1; }; }
	@echo ""
	@echo "==> Validating PDF..."
	@pdfinfo $@ | head -5
	@echo ""
	@echo "✓ Successfully built $@"
	@echo ""

# Individual variant targets
software-developer: $(OUTPUT_DIR)/software-developer.pdf

devops-engineer: $(OUTPUT_DIR)/devops-engineer.pdf

cloud-engineer: $(OUTPUT_DIR)/cloud-engineer.pdf

# Test data completeness (needs PDFs) + the phase-5 substrate (hermetic, no PDFs)
test: $(foreach v,$(VARIANTS),$(OUTPUT_DIR)/$(v).pdf)
	@echo "==> Running data completeness tests..."
	@$(PYTHON) scripts/test_data_completeness.py
	@$(MAKE) --no-print-directory test-substrate PYTHON=$(PYTHON)

# Generate ATS-friendly plain-text versions (independent of LaTeX)
ATS_OUTPUT_DIR = output/ats
$(ATS_OUTPUT_DIR)/%.txt: $(DATA_DIR)/*.yaml scripts/generate_ats.py
	@mkdir -p $(ATS_OUTPUT_DIR)
	$(PYTHON) scripts/generate_ats.py --variant $* --data-dir $(DATA_DIR) --output $@

ats-all: $(foreach v,$(VARIANTS),$(ATS_OUTPUT_DIR)/$(v).txt)
	@echo "✓ All ATS-friendly versions generated in $(ATS_OUTPUT_DIR)"

# Every hermetic test (no PDFs needed): each scripts/test_*.py except the
# PDF completeness check, so a new test file runs without editing this list.
test-substrate:
	@set -e; for f in scripts/test_*.py; do \
		m=$$(basename $$f .py); [ "$$m" = test_data_completeness ] && continue; \
		echo "==> $$m"; $(PYTHON) -m scripts.$$m; \
	done

# Clean all generated files
clean:
	@echo "==> Cleaning generated files..."
	rm -rf $(OUTPUT_DIR)/*
	@echo "✓ Clean complete"

# Job aggregator
jobs:
	$(PYTHON) -m scripts.job_aggregator.cli search

jobs-notify:
	$(PYTHON) -m scripts.job_aggregator.cli search --notify

jobs-list:
	$(PYTHON) -m scripts.job_aggregator.cli list

jobs-tui:
	$(PYTHON) -m scripts.job_aggregator.tui

# Applications (per-posting tailored CVs)
applications:
	$(PYTHON) -m scripts.application build-all

applications-status:
	$(PYTHON) -m scripts.application status

# Open a CV PDF in the default viewer.
#   make open                      interactive picker (fzf, with page-1 preview)
#   make open VIEW=cloud-engineer      open a specific variant directly
#   make open-app SLUG=<slug>          open an application's tailored cv.pdf
open:
	@$(PYTHON) -m scripts.application open $(VIEW)

open-app:
	@$(PYTHON) -m scripts.application open $(SLUG)

# The same inner targets run in GitHub Actions and the local container.
.PHONY: ci ci-inner ci-variant ci-applications ci-setup print-texlive-image
print-texlive-image:
	@echo $(TEXLIVE_IMAGE)

ci-setup:
	apt-get update
	apt-get install -y python3 python3-venv poppler-utils make
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install -r requirements.txt

ci-variant:
	$(MAKE) -B $(OUTPUT_DIR)/$(VARIANT).pdf $(ATS_OUTPUT_DIR)/$(VARIANT).txt PYTHON=$(PYTHON)
	$(PYTHON) scripts/test_data_completeness.py --variant $(VARIANT)

ci-applications:
	$(PYTHON) -m scripts.application build-all

ci-inner:
	$(MAKE) ci-setup
	@for variant in $(VARIANTS); do $(MAKE) ci-variant VARIANT=$$variant PYTHON=$(VENV)/bin/python || exit $$?; done
	$(MAKE) test-substrate PYTHON=$(VENV)/bin/python
	$(MAKE) ci-applications PYTHON=$(VENV)/bin/python

# The venv lives inside the container, and a rootful runtime hands the build
# output back to you, so `make ci` leaves no root-owned files in the checkout.
ci:
	@runtime=$$(command -v docker || command -v podman) || { echo "Install docker or podman to run CI" >&2; exit 1; }; \
	owner="$$(id -u):$$(id -g)"; \
	case "$$runtime" in *podman) owner= ;; esac; \
	"$$runtime" info 2>/dev/null | grep -qi rootless && owner=; \
	"$$runtime" run --rm -e CI_OWNER="$$owner" -e PYTHONDONTWRITEBYTECODE=1 \
		-v "$(CURDIR):/workspace" -w /workspace $(TEXLIVE_IMAGE) \
		sh -c 'make ci-inner VENV=/opt/venv; rc=$$?; [ -z "$$CI_OWNER" ] || chown -R "$$CI_OWNER" output applications; exit $$rc'
