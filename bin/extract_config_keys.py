#!/usr/bin/env python3
"""
Stalwart Mail Server Configuration Key Extractor

This utility analyzes the Stalwart source code to extract all configuration keys
that can be used in config.toml files. It parses Rust files looking for patterns
like config.property(), config.value(), config.sub_keys(), etc.

Author: Jim Dunphy 10/17/2025
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Set, Dict, List, Tuple
import json


class ConfigKeyExtractor:
    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.config_keys: Set[str] = set()
        self.key_contexts: Dict[str, List[Dict]] = defaultdict(list)

        # Regex patterns to match config access patterns
        self.patterns = [
            # Matches: config.property(("key", "subkey", "leaf"))
            # Matches: config.value(("key", "subkey"))
            # Matches: config.value_require(("key", "subkey"))
            r'config\.(?:property|value|value_require|value_require_non_empty|property_require|property_or_default|properties)\s*(?:<[^>]+>)?\s*\(\s*\(([^)]+)\)',

            # Matches: config.property("simple.key")
            # Matches: config.value("simple.key")
            r'config\.(?:property|value|value_require|value_require_non_empty|property_require|property_or_default)\s*(?:<[^>]+>)?\s*\(\s*"([^"]+)"\s*\)',

            # Matches: config.sub_keys("key", ".suffix")
            # Matches: config.sub_keys("key.subkey", ".suffix")
            r'config\.sub_keys(?:_with_suffixes)?\s*\(\s*"([^"]+)"',

            # Matches: config.values("key.path")
            r'config\.values\s*\(\s*"([^"]+)"\s*\)',

            # Matches: ("key", id, "subkey") within property/value calls
            # Matches: ("key", id.as_str(), "subkey")
            r'\(\s*\(\s*"([^"]+)"\s*,\s*[^,)]+\s*,\s*"([^"]+)"\s*\)',
        ]

    def normalize_key(self, parts: List[str]) -> str:
        """Convert key parts to a normalized dotted key."""
        normalized = []
        for part in parts:
            part = part.strip().strip('"').strip("'")
            if part and not part.startswith('(') and part != 'id' and part != 'prefix':
                normalized.append(part)
        return '.'.join(normalized) if normalized else None

    def extract_key_from_tuple(self, tuple_str: str) -> str:
        """Extract configuration key from a tuple like ("queue", "tls", "dane")."""
        # Remove outer parentheses if present
        tuple_str = tuple_str.strip()
        if tuple_str.startswith('(') and tuple_str.endswith(')'):
            tuple_str = tuple_str[1:-1]

        # Split by comma and extract parts
        parts = []
        for part in tuple_str.split(','):
            part = part.strip()
            # Match quoted strings
            match = re.search(r'["\']([^"\']+)["\']', part)
            if match:
                parts.append(match.group(1))
            else:
                # Non-quoted part - likely a variable like 'id', 'id.as_str()', 'prefix', 'ip.to_string()', 'option'
                # Check if it's a variable identifier (not empty and not a keyword)
                var_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)', part)
                if var_match:
                    var_name = var_match.group(1)
                    # Replace common variable names with template placeholder
                    if var_name in ('id', 'prefix', 'key', 'name', 'ip', 'option'):
                        parts.append('<id>')

        return '.'.join(parts) if parts else None

    def extract_keys_from_file(self, file_path: Path):
        """Extract configuration keys from a single Rust file."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            return

        # Pattern 1: Tuple-based config access like config.property(("key", "subkey"))
        # Also matches chained calls like .property_or_default(("key", id, "subkey"))
        # Supports Rust turbofish syntax with nested generics: config.properties::<Option<u32>>((...))
        # Requires either 'config.' OR leading '.' to avoid matching parse_value(), etc.
        # Handles nested parentheses (e.g., ip.to_string()) and additional arguments after tuple
        # Allows whitespace/newlines between opening parens for multi-line formatted code
        # Pattern breakdown: ( optional-space ( [non-parens OR (nested-parens)] ) followed by ) or ,
        tuple_pattern = r'(?:config\.|\.)(?:property|value|value_require|value_require_non_empty|property_require|property_or_default|property_or_else|value_or_else|properties)\s*(?:::<[^(]+)?\s*\(\s*\(((?:[^()]|\([^()]*\))+)\)(?=\s*[\),])'
        for match in re.finditer(tuple_pattern, content):
            key = self.extract_key_from_tuple(match.group(1))
            if key:
                self.config_keys.add(key)
                self.key_contexts[key].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'tuple'
                })

        # Pattern 2: Simple string-based config access like config.property("simple.key")
        # Also matches chained calls like .property_or_default("resolver.edns", "true")
        # The [^)]* allows for additional arguments after the key (like default values)
        # Supports Rust turbofish syntax with nested generics: config.property::<Option<u32>>("key")
        # Requires either 'config.' OR leading '.' to avoid matching parse_value(), etc.
        simple_pattern = r'(?:config\.|\.)(?:property|value|value_require|value_require_non_empty|property_require|property_or_default|property_or_else|value_or_else|properties)\s*(?:::<[^(]+)?\s*\(\s*"([^"]+)"[^)]*\)'
        for match in re.finditer(simple_pattern, content):
            key = match.group(1).strip()
            if key and not key.startswith('&'):
                self.config_keys.add(key)
                self.key_contexts[key].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'string'
                })

        # Pattern 3: config.sub_keys("base.key", ".suffix") and config.sub_keys_with_suffixes
        sub_key_pattern = r'config\.sub_keys\s*\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?\s*\)'
        for match in re.finditer(sub_key_pattern, content):
            base_key = match.group(1).strip()
            suffix = match.group(2).strip('.') if match.group(2) else None

            self.config_keys.add(base_key)
            self.key_contexts[base_key].append({
                'file': str(file_path.relative_to(self.source_dir)),
                'type': 'sub_keys'
            })

            if suffix:
                template_key = f"{base_key}.<id>.{suffix}"
                self.config_keys.add(template_key)
                self.key_contexts[template_key].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'sub_keys_template'
                })

        # Pattern 3b: config.sub_keys_with_suffixes("base.key", &[".suffix1", ".suffix2"])
        sub_key_suffixes_pattern = r'config\.sub_keys_with_suffixes\s*\(\s*"([^"]+)"\s*,\s*&\[(.*?)\]'
        for match in re.finditer(sub_key_suffixes_pattern, content, re.DOTALL):
            base_key = match.group(1).strip()
            suffixes_str = match.group(2)

            self.config_keys.add(base_key)
            self.key_contexts[base_key].append({
                'file': str(file_path.relative_to(self.source_dir)),
                'type': 'sub_keys_with_suffixes'
            })

            # Extract all suffixes from the array
            suffix_matches = re.findall(r'"\.?([^"]+)"', suffixes_str)
            for suffix in suffix_matches:
                template_key = f"{base_key}.<id>.{suffix}"
                self.config_keys.add(template_key)
                self.key_contexts[template_key].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'sub_keys_with_suffixes_template'
                })

        # Pattern 4: config.values("key.path") and config.values_or_else(...)
        # Also matches chained calls like .values("resolver.custom")
        # Requires either 'config.' OR leading '.' to avoid false positives
        values_pattern = r'(?:config\.|\.)(?:values|values_or_else)\s*\(\s*"([^"]+)"[^)]*\)'
        for match in re.finditer(values_pattern, content):
            key = match.group(1).strip()
            if key:
                self.config_keys.add(key)
                self.key_contexts[key].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'values'
                })

        # Pattern 5: config.iterate_prefix("key.path")
        # This iterates over keys like "key.path.id.subkey", generating dynamic keys
        iterate_prefix_pattern = r'config\.iterate_prefix\s*\(\s*"([^"]+)"\s*\)'
        for match in re.finditer(iterate_prefix_pattern, content):
            prefix = match.group(1).strip()
            if prefix:
                # Add the base prefix
                self.config_keys.add(prefix)
                self.key_contexts[prefix].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'iterate_prefix'
                })

                # Add template for dynamic keys: prefix.<id>.<key>
                template_key = f"{prefix}.<id>.<key>"
                self.config_keys.add(template_key)
                self.key_contexts[template_key].append({
                    'file': str(file_path.relative_to(self.source_dir)),
                    'type': 'iterate_prefix_template'
                })

    def scan_codebase(self):
        """Scan all Rust files in the codebase."""
        rust_files = list(self.source_dir.rglob('*.rs'))
        print(f"Scanning {len(rust_files)} Rust files...", file=sys.stderr)

        for file_path in rust_files:
            # Skip test files
            if '/tests/' in str(file_path) or file_path.name.endswith('_test.rs'):
                continue

            self.extract_keys_from_file(file_path)

        print(f"Found {len(self.config_keys)} unique configuration keys", file=sys.stderr)

    def build_hierarchy(self) -> Dict:
        """Build a hierarchical structure of configuration keys."""
        hierarchy = {}

        for key in sorted(self.config_keys):
            parts = key.split('.')
            current = hierarchy

            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {'_children': {}, '_full_key': '.'.join(parts[:i+1])}
                current = current[part]['_children']

        return hierarchy

    def print_hierarchy(self, node: Dict, indent: int = 0, prefix: str = ""):
        """Print the configuration hierarchy as a tree."""
        if not node:
            return

        items = sorted(node.items())
        for i, (key, value) in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "

            print(f"{prefix}{connector}{key}")

            if value.get('_children'):
                extension = "    " if is_last else "│   "
                self.print_hierarchy(value['_children'], indent + 1, prefix + extension)

    def print_flat_list(self):
        """Print all configuration keys as a flat list."""
        for key in sorted(self.config_keys):
            print(key)

    def export_json(self, output_file: Path):
        """Export configuration keys to JSON."""
        data = {
            'keys': sorted(list(self.config_keys)),
            'hierarchy': self.build_hierarchy(),
            'contexts': {k: v for k, v in self.key_contexts.items()}
        }

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Exported to {output_file}", file=sys.stderr)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract configuration keys from Stalwart Mail Server source code'
    )
    parser.add_argument(
        'source_dir',
        type=Path,
        nargs='?',
        default=Path.cwd(),
        help='Path to Stalwart source directory (default: current directory)'
    )
    parser.add_argument(
        '--format',
        choices=['tree', 'flat', 'json'],
        default='tree',
        help='Output format (default: tree)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file for JSON format'
    )
    parser.add_argument(
        '--filter',
        help='Filter keys by prefix (e.g., "queue" or "server.listener")'
    )

    args = parser.parse_args()

    source_dir = args.source_dir
    if not source_dir.exists():
        print(f"Error: Directory {source_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    # Find the crates directory
    crates_dir = source_dir / 'crates'
    if not crates_dir.exists():
        crates_dir = source_dir

    extractor = ConfigKeyExtractor(crates_dir)
    extractor.scan_codebase()

    # Apply filter if specified
    if args.filter:
        filtered_keys = {k for k in extractor.config_keys if k.startswith(args.filter)}
        extractor.config_keys = filtered_keys
        print(f"Filtered to {len(filtered_keys)} keys matching '{args.filter}'", file=sys.stderr)

    print("", file=sys.stderr)  # Blank line before output

    # Output results
    if args.format == 'flat':
        extractor.print_flat_list()
    elif args.format == 'json':
        output_file = args.output or (source_dir / 'config_keys.json')
        extractor.export_json(output_file)
    else:  # tree
        hierarchy = extractor.build_hierarchy()
        extractor.print_hierarchy(hierarchy)


if __name__ == '__main__':
    main()
