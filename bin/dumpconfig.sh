#!/bin/bash
export PATH=/opt/stalwart/bin:$PATH
export URL=https://127.0.0.1:443
export CREDENTIALS="CHANGE_ME"


stalwart-cli server list-config | python3 -c '
import sys, re

def flush_record(key, value_lines):
    if key is None: return
    full_value = "\n".join(value_lines).strip()
    if not full_value: full_value = "<no value>"
    print(f"\x1b[1mKey:\x1b[0m   {key}\n📝 \x1b[1mValue:\x1b[0m {full_value}\n")

current_key, current_value_lines = None, []
pat = re.compile(r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")

for line in sys.stdin:
    if line.startswith("+--"): continue
    match = pat.match(line.rstrip())
    if not match: continue
    key_part, val_part = match.groups()
    if key_part:
        flush_record(current_key, current_value_lines)
        current_key, current_value_lines = key_part, [val_part]
    elif current_key is not None:
        current_value_lines.append(val_part)

flush_record(current_key, current_value_lines)
'
