#!/usr/bin/env python3
"""Generate LaTeX CV from YAML data using Jinja2 templates."""

import argparse
import yaml
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

def escape_latex(text):
    """Escape LaTeX special characters."""
    chars = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }
    return ''.join(chars.get(c, c) for c in str(text))

def filter_by_tags(items, tags):
    """Filter items by tags for variant.

    Args:
        items: List of items (jobs, strengths, etc.) with 'tags' field
        tags: List of tags to filter by

    Returns:
        List of items that have at least one matching tag
    """
    if not tags:
        return items
    return [item for item in items if any(tag in item.get('tags', []) for tag in tags)]

def load_yaml_data(data_dir):
    """Load all YAML files from data directory."""
    data = {}
    data_path = Path(data_dir)

    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    for yaml_file in data_path.glob('*.yaml'):
        with open(yaml_file) as f:
            data[yaml_file.stem] = yaml.safe_load(f)

    return data

def main():
    parser = argparse.ArgumentParser(description='Generate LaTeX CV from YAML')
    parser.add_argument('--variant', required=True, help='CV variant (e.g., engineering-manager)')
    parser.add_argument('--data-dir', default='data/', help='YAML data directory')
    parser.add_argument('--template', help='Jinja2 template path (optional, auto-detected from variant)')
    parser.add_argument('--output', required=True, help='Output .tex file')
    args = parser.parse_args()

    # Load YAML data
    print(f"Loading YAML data from {args.data_dir}...")
    data = load_yaml_data(args.data_dir)
    data['variant'] = args.variant

    print(f"Loaded data files: {', '.join(data.keys())}")

    # Setup Jinja2
    template_path = args.template or f'templates/{args.variant}/template.tex.j2'
    template_file = Path(template_path)

    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    print(f"Using template: {template_path}")

    env = Environment(loader=FileSystemLoader(template_file.parent))
    env.filters['escape_latex'] = escape_latex
    env.filters['filter_by_tags'] = filter_by_tags

    # Render template
    print(f"Rendering template for variant: {args.variant}")
    template = env.get_template(template_file.name)
    output = template.render(**data)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output)

    print(f"✓ Generated {args.output}")
    print(f"  Lines: {len(output.splitlines())}")
    print(f"  Size: {len(output)} bytes")

if __name__ == '__main__':
    main()
