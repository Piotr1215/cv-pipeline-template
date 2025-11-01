.PHONY: all clean help test software-developer devops-engineer cloud-engineer

VARIANTS = software-developer devops-engineer cloud-engineer
DATA_DIR = data
TEMPLATE_DIR = templates
OUTPUT_DIR = output/generated
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
	@echo "  test                 - Verify all YAML data is rendered in PDFs"
	@echo "  clean                - Remove all generated files"
	@echo "  help                 - Show this help message"
	@echo ""
	@echo "Build pipeline:"
	@echo "  YAML -> Python -> .tex -> pdflatex -> .pdf -> test"

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

# Clean all generated files
clean:
	@echo "==> Cleaning generated files..."
	rm -rf $(OUTPUT_DIR)/*
	@echo "✓ Clean complete"
