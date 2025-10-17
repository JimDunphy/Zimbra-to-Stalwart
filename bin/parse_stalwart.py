#!/usr/bin/env python3

#
# usage: stalwart-cli server list-config | ./parse_stalwart.py
#
import sys
import re

def flush_record(key, value_lines):
    """Prints the formatted record."""
    if key is None:
        return
    
    # Join the list of value lines into a single string
    full_value = "\n".join(value_lines).strip()
    
    # Set placeholder if the final value is empty
    if not full_value:
        full_value = "<no value>"
        
    print(f"\x1b[1mKey:\x1b[0m   {key}")
    print(f"\x1b[1mValue:\x1b[0m {full_value}\n")

# --- Main script ---
current_key = None
current_value_lines = []
line_pattern = re.compile(r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")

for line in sys.stdin:
    # Skip the table's horizontal rule lines
    if line.startswith('+--'):
        continue

    match = line_pattern.match(line.rstrip())
    if not match:
        continue

    key_part, val_part = match.groups()

    if key_part:  # This line starts a NEW record
        # First, print the previous record we finished collecting
        flush_record(current_key, current_value_lines)
        
        # Then, start the new record
        current_key = key_part
        current_value_lines = [val_part]
    elif current_key is not None:  # This is a continuation line for the CURRENT record
        current_value_lines.append(val_part)

# After the loop, print the very last record
flush_record(current_key, current_value_lines)
