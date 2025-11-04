.PHONY: all clean help test software-developer devops-engineer cloud-engineer ats ats-all

VARIANTS = software-developer devops-engineer cloud-engineer
DATA_DIR = data
TEMPLATE_DIR = templates
OUTPUT_DIR = output/generated
ATS_OUTPUT_DIR = output/ats
PYTHON = python3

all: $(foreach v,$(VARIANTS),$(OUTPUT_DIR)/$(v).pdf) test

help:
	@echo "CV Pipeline Build System"
	@echo ""
	@echo "Available targets:"
	@echo "  all                  - Build all CV variants and run tests"
	@echo "  software-developer   - Build Software Developer CV"
	@echo "  devops-engineer      - Build DevOps Engineer CV"
	@echo "  cloud-engineer       - Build Cloud Engineer CV"
	@echo "  ats-all              - Generate all ATS-friendly text versions"
	@echo "  test                 - Verify all YAML data is rendered in PDFs"
	@echo "  clean                - Remove all generated files"
	@echo "  help                 - Show this help message"
	@echo ""
	@echo "Build pipeline:"
	@echo "  PDF:  YAML -> Python -> .tex -> pdflatex -> .pdf -> test"
	@echo "  ATS:  YAML -> Python -> .txt (plain text, ATS-optimized)"

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
	cd $(OUTPUT_DIR) && pdflatex -interaction=nonstopmode -halt-on-error $*.tex
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

# Test data completeness
test: $(foreach v,$(VARIANTS),$(OUTPUT_DIR)/$(v).pdf)
	@echo "==> Running data completeness tests..."
	@$(PYTHON) scripts/test_data_completeness.py

# Generate ATS-friendly text versions
$(ATS_OUTPUT_DIR)/%.txt: $(DATA_DIR)/*.yaml scripts/generate_ats.py
	@echo "==> Generating ATS-friendly $*.txt..."
	@mkdir -p $(ATS_OUTPUT_DIR)
	$(PYTHON) scripts/generate_ats.py \
		--variant $* \
		--data-dir $(DATA_DIR) \
		--output $@
	@echo ""

# Generate all ATS versions
ats-all: $(foreach v,$(VARIANTS),$(ATS_OUTPUT_DIR)/$(v).txt)
	@echo "✓ All ATS-friendly versions generated"
	@echo ""
	@echo "Generated files:"
	@ls -lh $(ATS_OUTPUT_DIR)/*.txt

# Clean all generated files
clean:
	@echo "==> Cleaning generated files..."
	rm -rf $(OUTPUT_DIR)/*
	rm -rf $(ATS_OUTPUT_DIR)/*
	@echo "✓ Clean complete"
