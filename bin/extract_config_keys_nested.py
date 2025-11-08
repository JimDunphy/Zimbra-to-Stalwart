#!/usr/bin/env python3
"""
Extract Stalwart configuration keys from Rust source files using serde struct parsing.
This approach analyzes Rust structs with #[derive(Deserialize)] to extract schema information.

Complementary to extract_config_keys.py which uses runtime pattern matching.

Usage:
    ./extract_config_keys_nested.py /path/to/stalwart/crates > stalwart_config_keys.md
    ./extract_config_keys_nested.py /path/to/stalwart/crates --format json > config_schema.json

Author: Jim Dunphy 10/17/2025
"""

import os
import re
import sys
import json
from pathlib import Path
from collections import defaultdict
import argparse

# ---------- Parse Arguments ----------
parser = argparse.ArgumentParser(
    description='Extract configuration keys from Stalwart structs (serde schema approach)'
)
parser.add_argument(
    'source_dir',
    type=Path,
    help='Path to Stalwart crates directory'
)
parser.add_argument(
    '--format',
    choices=['markdown', 'json'],
    default='markdown',
    help='Output format (default: markdown)'
)
args = parser.parse_args()

SOURCE_DIR = args.source_dir

if not SOURCE_DIR.exists():
    print(f"Error: Directory {SOURCE_DIR} does not exist", file=sys.stderr)
    sys.exit(1)

# ---------- Regex Patterns ----------
struct_header = re.compile(r"^\s*pub\s+struct\s+(\w+)\s*\{")
field_line = re.compile(r"^\s*pub\s+(\w+)\s*:\s*([A-Za-z0-9_<>\[\]_]+)")
serde_rename = re.compile(r'#\[serde\(rename\s*=\s*"([^"]+)"\)\]')
serde_flatten = re.compile(r"#\[serde\(flatten\)\]")

# ---------- Data Structures ----------
structs = defaultdict(list)
current_struct = None
current_rename = None
current_flatten = False

# ---------- Pass 1: Collect all structs and fields ----------
for path in SOURCE_DIR.rglob("*.rs"):
    with path.open(errors="ignore") as f:
        for line_no, line in enumerate(f, 1):
            # Detect struct
            m = struct_header.match(line)
            if m:
                current_struct = m.group(1)
                continue

            # Handle serde rename or flatten
            if line.strip().startswith("#[serde"):
                r = serde_rename.search(line)
                if r:
                    current_rename = r.group(1)
                elif serde_flatten.search(line):
                    current_flatten = True
                continue

            # Detect field
            if current_struct:
                m = field_line.match(line)
                if m:
                    field, ftype = m.group(1), m.group(2)
                    key = current_rename or field
                    structs[current_struct].append({
                        "key": key,
                        "type": ftype,
                        "file": str(path.relative_to(SOURCE_DIR)),
                        "line": line_no,
                        "flatten": current_flatten,
                    })
                    current_rename = None
                    current_flatten = False

                elif line.strip().startswith("}"):
                    current_struct = None

# ---------- Pass 2: Recursively expand dotted keys ----------
def expand_struct(struct_name, prefix=""):
    results = []
    for field in structs.get(struct_name, []):
        full_key = f"{prefix}.{field['key']}" if prefix else field["key"]
        results.append({
            "key": full_key,
            "type": field["type"],
            "file": field["file"],
            "line": field["line"],
        })
        # If this field is itself a struct, recurse
        sub_type = field["type"].replace("Option<", "").replace("Vec<", "").rstrip(">")
        if sub_type in structs and not field["flatten"]:
            results.extend(expand_struct(sub_type, full_key))
        elif field["flatten"]:
            # Flatten merges subfields into same prefix
            results.extend(expand_struct(sub_type, prefix))
    return results

# ---------- Pass 3: Find actual config root structs ----------
# Look for structs that are actually used in config parsing rather than guessing
roots = set()
config_parse_patterns = [
    re.compile(r'(\w+)::parse\s*\('),  # MyConfig::parse(
    re.compile(r'from_str::<(\w+)>'),  # from_str::<MyConfig>
    re.compile(r'deserialize.*?<(\w+)>'),  # deserialize::<MyConfig>
]

# Scan for actual usage of structs in parsing contexts
for path in SOURCE_DIR.rglob("*.rs"):
    with path.open(errors="ignore") as f:
        content = f.read()
        for pattern in config_parse_patterns:
            for match in pattern.finditer(content):
                struct_name = match.group(1)
                if struct_name in structs:
                    roots.add(struct_name)

# Fallback: if we found no roots via parsing patterns, use heuristic
if not roots:
    print("Warning: No config parsing patterns found, using name-based heuristic", file=sys.stderr)
    roots = {name for name in structs if name.lower().endswith("config")}
else:
    print(f"Found {len(roots)} root config structs via parsing patterns", file=sys.stderr)

# ---------- Collect all expanded keys ----------
all_keys = []
seen = set()
for root in sorted(roots):
    for r in expand_struct(root):
        if r["key"] not in seen:
            seen.add(r["key"])
            all_keys.append(r)

# ---------- Generate Output ----------
if args.format == 'json':
    # JSON output
    json_output = {
        "extraction_method": "serde-schema",
        "total_keys": len(seen),
        "total_structs": len(structs),
        "root_structs": list(sorted(roots)),
        "keys": all_keys
    }
    print(json.dumps(json_output, indent=2))
else:
    # Markdown output
    output = []
    output.append("# Stalwart Configuration Keys (Schema-based Extraction)")
    output.append("")
    output.append("Extracted via serde struct parsing. Complementary to runtime pattern matching.")
    output.append("")
    output.append("**Note:** This extraction shows struct definitions. Keys accessed dynamically")
    output.append("(e.g., `queue.connection.<id>`, `server.listener.<id>`) may not appear with `<id>` placeholders.")
    output.append("")
    output.append(f"**Total Keys:** {len(seen)} | **Structs Analyzed:** {len(structs)} | **Root Configs:** {len(roots)}")
    output.append("")
    output.append("| Config Key | Type | Source |")
    output.append("|------------|------|--------|")

    for r in all_keys:
        output.append(
            f"| `{r['key']}` | `{r['type']}` | `{r['file']}:{r['line']}` |"
        )

    print("\n".join(output))

print(f"# Extracted {len(seen)} unique keys from {len(structs)} structs.", file=sys.stderr)

