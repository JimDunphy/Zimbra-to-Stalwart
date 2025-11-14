# stalwart-spam-rules.py

Bulk helper to inspect and manage Stalwart spam filter rules the same way you would curate SpamAssassin rule packs. It can read from a live server via the management API or from the offline dumps under `stalwart-scripts/etc/`.

## Prerequisites

- Python 3.9+.
- `pip install -r requirements.txt` (needs `requests`).
- Management API credentials (either `STALWART_TOKEN` or basic auth user/pass) when talking to a running server.

## Quick Start

```bash
# List rules from a live node (defaults to http://127.0.0.1:8080)
./stalwart-spam-rules.py --server mail.example.com --token $STALWART_TOKEN --list

# Export everything to JSON for offline editing
./stalwart-spam-rules.py --server mail.example.com \
    --token $STALWART_TOKEN --export spam-rules.json --pretty

# Import edited JSON, replacing existing rules and scores
./stalwart-spam-rules.py --server mail.example.com \
    --token $STALWART_TOKEN --import-file spam-rules.json --replace
```

## Offline Inspection

Use the captured data inside `stalwart-scripts/etc/` when a server is not available:

```bash
./stalwart-spam-rules.py --config-file etc/config.toml --key-dump etc/all_keys.out --list
./stalwart-spam-rules.py --config-file etc/config.toml --export offline-rules.json
```

`--config-file` expects the flattened `key = value` TOML, while `--key-dump` parses the colored `all_keys.out`. Provide either (or both) to merge sources.

## JSON Layout

`--export` produces:

- `metadata`: timestamp + source summary.
- `rules[]`: rule id, scope, priority, enable state, optional description, condition list (`if / then` pairs plus default), and any additional keys.
- `scores[]`: each symbol from `spam-filter.list.scores.*` with its action/score.

You can edit the JSON in bulk (e.g., tweak `priority`, update expressions, change scores) and feed it back with `--import-file`. Use `--dry-run` first to see how many operations would be issued, and `--replace` if you want to wipe existing `spam-filter.rule.*` / `spam-filter.list.scores.*` keys before applying.

## Tips

- Add `--include-disabled` to inspect disabled rules alongside active ones.
- `--limit N` keeps the `--list` output manageable when auditing a small subset.
- Combine with `extract_config_keys_nested.py` to cross-reference where each tag or score is defined in the Rust sources; the exported file includes every tag the script sees in `then` expressions so you can search within it quickly.
- The management API defaults to `/api`. If your deployment proxies it elsewhere (e.g., `/manage`), use `--api-prefix /manage` or set `STALWART_API_PREFIX` so the script hits the right endpoints.
