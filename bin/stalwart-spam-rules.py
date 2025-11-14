#!/usr/bin/env python3
"""
Stalwart Spam Rule Management Tool

List, export, and re-import Stalwart spam filter rules + scores in bulk so
contributors can edit them offline similar to SpamAssassin rule bundles.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Try `pip install requests`.", file=sys.stderr)
    sys.exit(1)


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TAG_RE = re.compile(r"'([A-Z0-9_]{2,})'")
DEFAULT_SERVER = os.getenv("STALWART_SERVER", "http://127.0.0.1:8080")


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def to_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def to_int(value: Optional[str], default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def ensure_str(value: Optional[object]) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def zero_index(idx: int) -> str:
    return f"{idx:04d}"


def normalize_server_url(server: Optional[str]) -> Optional[str]:
    if not server:
        return None
    server = server.strip()
    if not server:
        return None
    if "://" not in server:
        server = f"https://{server}"
    parsed = urlparse(server)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid server URL: {server}")
    return server


@dataclass
class ConditionItem:
    expr: str
    result: str


@dataclass
class RuleRecord:
    rule_id: str
    enabled: bool = True
    priority: int = 0
    scope: str = "any"
    description: Optional[str] = None
    conditions: List[ConditionItem] = field(default_factory=list)
    default: Optional[str] = None
    extras: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "id": self.rule_id,
            "enabled": self.enabled,
            "priority": self.priority,
            "scope": self.scope,
            "conditions": {
                "if": [{"if": item.expr, "then": item.result} for item in self.conditions],
                "else": self.default,
            },
        }
        if self.description is not None:
            payload["description"] = self.description
        if self.extras:
            payload["extras"] = self.extras
        tags = self.tags()
        if tags:
            payload["tags"] = tags
        return payload

    def tags(self) -> List[str]:
        tags: List[str] = []
        for item in self.conditions:
            tags.extend(TAG_RE.findall(item.result))
        if self.default:
            tags.extend(TAG_RE.findall(self.default))
        # Preserve order but drop duplicates
        seen = set()
        ordered = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                ordered.append(tag)
        return ordered


class SettingsClient:
    """Use either the management API or offline dumps to read/write settings."""

    def __init__(
        self,
        server: Optional[str],
        token: Optional[str],
        username: Optional[str],
        password: Optional[str],
        api_prefix: str,
        verify_tls: bool = True,
        config_file: Optional[Path] = None,
        key_dump: Optional[Path] = None,
        timeout: int = 30,
    ):
        self.timeout = timeout
        self.session: Optional[requests.Session] = None
        normalized_server = normalize_server_url(server)
        self.server = normalized_server.rstrip("/") if normalized_server else None
        self.api_prefix = "/" + api_prefix.strip("/") if api_prefix else "/api/manage"
        self.mode = "remote" if self.server else "offline"
        self.verify_tls = verify_tls
        self.offline_settings: Dict[str, str] = {}

        if self.mode == "remote":
            self.session = requests.Session()
            self.session.headers["Accept"] = "application/json"
            auth_token = token or os.getenv("STALWART_TOKEN")
            if auth_token:
                self.session.headers["Authorization"] = f"Bearer {auth_token}"
            elif username:
                if password is None:
                    password = os.getenv("STALWART_PASSWORD")
                if password is None:
                    import getpass

                    password = getpass.getpass(f"Password for {username}: ")
                self.session.auth = (username, password)
        else:
            if not (config_file or key_dump):
                raise ValueError("Offline mode requires --config-file or --key-dump")
            if config_file:
                self.offline_settings.update(load_flat_config(config_file))
            if key_dump:
                self.offline_settings.update(load_key_dump(key_dump))

    def fetch(self, prefixes: Iterable[str]) -> Dict[str, str]:
        if self.mode == "remote":
            params = {}
            prefix_list = [p.rstrip(".") for p in prefixes]
            if prefix_list:
                params["prefixes"] = ",".join(prefix_list)
            url = self.build_url("settings/keys")
            response = self.session.get(url, params=params, timeout=self.timeout, verify=self.verify_tls)
            response.raise_for_status()
            payload = response.json()
            return payload.get("data", {})

        # Offline mode
        results: Dict[str, str] = {}
        for prefix in prefixes:
            prefix = prefix.rstrip(".")
            prefix_dot = prefix + "."
            for key, value in self.offline_settings.items():
                if key == prefix or key.startswith(prefix_dot):
                    results[key] = value
        return results

    def clear_prefix(self, prefix: str) -> None:
        if self.mode != "remote":
            raise RuntimeError("Clearing prefixes is only supported against a live server.")
        url = self.build_url(f"settings/{prefix}")
        response = self.session.delete(url, timeout=self.timeout, verify=self.verify_tls)
        response.raise_for_status()

    def apply(self, operations: List[Dict[str, object]]) -> None:
        if self.mode != "remote":
            raise RuntimeError("Import only works against a live server.")
        url = self.build_url("settings")
        response = self.session.post(url, json=operations, timeout=self.timeout, verify=self.verify_tls)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise RuntimeError(f"Settings update failed: {detail}")

    def source_label(self) -> str:
        if self.mode == "remote":
            return self.server or "unknown-server"
        return "offline"

    def build_url(self, path: str) -> str:
        base = self.server or ""
        if not base:
            raise RuntimeError("No server specified for remote operations.")
        return f"{base}{self.api_prefix}/{path.lstrip('/')}"


def load_flat_config(path: Path) -> Dict[str, str]:
    settings: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        settings[key] = value
    return settings


def load_key_dump(path: Path) -> Dict[str, str]:
    settings: Dict[str, str] = {}
    key: Optional[str] = None
    for raw_line in path.read_text().splitlines():
        line = strip_ansi(raw_line).strip()
        if "Key:" in line:
            key = line.split("Key:", 1)[1].strip()
        elif "Value:" in line and key:
            value = line.split("Value:", 1)[1].strip()
            if value == "<no value>":
                value = ""
            settings[key] = value
            key = None
    return settings


class RuleSet:
    def __init__(self, rules: List[RuleRecord], scores: Dict[str, Dict[str, object]]):
        self.rules = sorted(rules, key=lambda r: (r.priority, r.rule_id))
        self.scores = scores

    @classmethod
    def from_settings(cls, settings: Dict[str, str], include_disabled: bool = True) -> "RuleSet":
        rule_prefix = "spam-filter.rule."
        score_prefix = "spam-filter.list.scores."

        raw_rules: Dict[str, Dict[str, str]] = {}
        for key, value in settings.items():
            if key.startswith(rule_prefix):
                remainder = key[len(rule_prefix) :]
                rule_id, _, attr = remainder.partition(".")
                if not attr:
                    continue
                raw_rules.setdefault(rule_id, {})[attr] = value

        rules: List[RuleRecord] = []
        for rule_id, attrs in raw_rules.items():
            enabled = to_bool(attrs.get("enable"), True)
            if not enabled and not include_disabled:
                continue
            record = RuleRecord(
                rule_id=rule_id,
                enabled=enabled,
                priority=to_int(attrs.get("priority"), 0),
                scope=attrs.get("scope", "any"),
                description=attrs.get("description"),
            )

            condition_entries = {
                key[len("condition.") :]: value
                for key, value in attrs.items()
                if key.startswith("condition.")
            }
            grouped: Dict[str, Dict[str, str]] = {}
            for entry_key, value in condition_entries.items():
                idx, _, suffix = entry_key.partition(".")
                if not suffix:
                    continue
                grouped.setdefault(idx, {})[suffix] = value

            for idx in sorted(grouped.keys()):
                row = grouped[idx]
                if "if" in row and "then" in row:
                    record.conditions.append(ConditionItem(expr=row["if"], result=row["then"]))
                if "else" in row:
                    record.default = row["else"]

            ignore_keys = {"enable", "priority", "scope", "description"}
            ignore_keys.update(condition_entries.keys())
            for attr_key, attr_value in attrs.items():
                if attr_key not in ignore_keys and not attr_key.startswith("condition."):
                    record.extras[attr_key] = attr_value

            rules.append(record)

        scores: Dict[str, Dict[str, object]] = {}
        for key, value in settings.items():
            if key.startswith(score_prefix):
                symbol = key[len(score_prefix) :]
                entry = parse_score_entry(symbol, value)
                scores[symbol] = entry

        return cls(rules, scores)

    def summary_rows(self, max_length: int = 3) -> List[Tuple[str, str, str, str, str]]:
        rows: List[Tuple[str, str, str, str, str]] = []
        for record in self.rules:
            tags = record.tags()[:max_length]
            tag_strings = []
            for tag in tags:
                tag_strings.append(f"{tag}{self._score_hint(tag)}")
            if len(record.tags()) > max_length:
                tag_strings.append("…")
            condition_count = len(record.conditions)
            rows.append(
                (
                    record.rule_id,
                    record.scope,
                    str(record.priority),
                    "yes" if record.enabled else "no",
                    f"{condition_count} cond / tags: {', '.join(tag_strings) if tag_strings else '-'}",
                )
            )
        return rows

    def _score_hint(self, tag: str) -> str:
        entry = self.scores.get(tag)
        if not entry:
            return ""
        action = entry["action"]
        if action in {"reject", "discard"}:
            return f" ({action})"
        score = entry.get("value")
        if score is None:
            return ""
        return f" ({score:+.2f})"

    def to_export_dict(self, source_label: str) -> Dict[str, object]:
        metadata = {
            "exportedAt": datetime.now(timezone.utc).isoformat(),
            "source": source_label,
            "ruleCount": len(self.rules),
            "scoreCount": len(self.scores),
        }
        export = {
            "metadata": metadata,
            "rules": [rule.to_dict() for rule in self.rules],
            "scores": [
                {"id": symbol, **entry}
                for symbol, entry in sorted(self.scores.items())
            ],
        }
        return export


def parse_score_entry(symbol: str, raw_value: str) -> Dict[str, object]:
    lowered = raw_value.strip().lower()
    if lowered in {"reject", "discard"}:
        return {"action": lowered, "value": None, "raw": raw_value}
    try:
        score = float(raw_value)
        return {"action": "allow", "value": score, "raw": raw_value}
    except ValueError:
        return {"action": "custom", "value": None, "raw": raw_value}


def export_rules(rule_set: RuleSet, destination: Path, pretty: bool, source_label: str) -> None:
    export_data = rule_set.to_export_dict(source_label)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(export_data, handle, indent=2 if pretty else None, sort_keys=pretty)
        if not pretty:
            handle.write("\n")


def print_summary(rule_set: RuleSet, limit: Optional[int] = None) -> None:
    rows = rule_set.summary_rows()
    if limit is not None:
        rows = rows[:limit]

    headers = ["Rule", "Scope", "Priority", "Enabled", "Conditions / Tags"]
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def _format_row(row_values: List[str]) -> str:
        return "  ".join(value.ljust(widths[idx]) for idx, value in enumerate(row_values))

    print(_format_row(headers))
    print(_format_row(["-" * w for w in widths]))
    for row in rows:
        print(_format_row(list(row)))

    print(f"\nTotal rules: {len(rule_set.rules)} | Total scores: {len(rule_set.scores)}")


def build_import_payload(rules_json: Dict[str, object]) -> Tuple[List[Dict[str, object]], List[Tuple[str, str]]]:
    rule_entries = rules_json.get("rules", [])
    score_entries = rules_json.get("scores", [])

    operations: List[Dict[str, object]] = []
    for entry in rule_entries:
        rule_id = entry["id"]
        values = []
        values.append(("enable", ensure_str(entry.get("enabled", True)).lower()))
        values.append(("priority", ensure_str(entry.get("priority", 0))))
        values.append(("scope", ensure_str(entry.get("scope", "any"))))
        if entry.get("description") is not None:
            values.append(("description", ensure_str(entry["description"])))
        extras = entry.get("extras", {})
        for key, value in extras.items():
            values.append((key, ensure_str(value)))

        conditions = entry.get("conditions", {})
        condition_items = conditions.get("if", [])
        for idx, condition in enumerate(condition_items):
            slot = zero_index(idx)
            values.append((f"condition.{slot}.if", ensure_str(condition.get("if", ""))))
            values.append((f"condition.{slot}.then", ensure_str(condition.get("then", ""))))
        default_expr = conditions.get("else")
        if default_expr is not None:
            slot = zero_index(len(condition_items))
            values.append((f"condition.{slot}.else", ensure_str(default_expr)))

        operations.append(
            {
                "type": "insert",
                "prefix": f"spam-filter.rule.{rule_id}",
                "values": values,
                "assertEmpty": False,
            }
        )

    score_values: List[Tuple[str, str]] = []
    for entry in score_entries:
        symbol = entry["id"]
        raw_value = entry.get("raw")
        if raw_value is None:
            action = str(entry.get("action", "allow")).lower()
            if action in {"reject", "discard"}:
                raw_value = action
            else:
                raw_value = ensure_str(entry.get("value", 0))
        score_values.append((symbol, ensure_str(raw_value)))

    return operations, score_values


def main() -> None:
    parser = argparse.ArgumentParser(description="Stalwart spam rule bulk management helper.")
    parser.add_argument("--server", default=None, help="Base URL to the Stalwart management API.")
    parser.add_argument("--token", default=os.getenv("STALWART_TOKEN"), help="API token (env STALWART_TOKEN).")
    parser.add_argument("--username", help="Fallback HTTP basic auth username.")
    parser.add_argument("--password", help="Fallback HTTP basic auth password.")
    parser.add_argument("--api-prefix", default=os.getenv("STALWART_API_PREFIX", "/api"),
                        help="Path prefix for management endpoints (default: /api).")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS verification (development only).")
    parser.add_argument("--config-file", type=Path, help="Offline mode: flattened config file to read rules from.")
    parser.add_argument("--key-dump", type=Path, help="Offline mode: parsed `all_keys` dump to read rules from.")
    parser.add_argument("--list", action="store_true", help="Print a summary of the rules.")
    parser.add_argument("--export", type=Path, help="Write the rules and scores to JSON.")
    parser.add_argument("--import-file", type=Path, help="Read JSON created by --export and push to the server.")
    parser.add_argument("--replace", action="store_true", help="Clear existing spam-filter.rule and *.scores before import.")
    parser.add_argument("--dry-run", action="store_true", help="Show the operations that would run without calling the API.")
    parser.add_argument("--include-disabled", action="store_true", help="Include disabled rules in the listing/export.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON for --export.")
    parser.add_argument("--limit", type=int, help="Limit how many rules are shown in --list output.")

    args = parser.parse_args()

    server = args.server or (None if (args.config_file or args.key_dump) else DEFAULT_SERVER)
    client = SettingsClient(
        server=server,
        token=args.token,
        username=args.username,
        password=args.password,
        api_prefix=args.api_prefix,
        verify_tls=not args.insecure,
        config_file=args.config_file,
        key_dump=args.key_dump,
    )

    prefixes = ["spam-filter.rule", "spam-filter.list.scores"]
    settings = client.fetch(prefixes)
    rule_set = RuleSet.from_settings(settings, include_disabled=args.include_disabled)

    performed_action = False

    if args.list or (not args.export and not args.import_file):
        print_summary(rule_set, limit=args.limit)
        performed_action = True

    if args.export:
        export_rules(rule_set, args.export, pretty=args.pretty, source_label=client.source_label())
        print(f"Wrote {args.export} ({len(rule_set.rules)} rules / {len(rule_set.scores)} scores)")
        performed_action = True

    if args.import_file:
        if client.mode != "remote":
            parser.error("--import-file requires a live --server connection.")
        data = json.loads(args.import_file.read_text())
        operations, score_values = build_import_payload(data)
        if args.replace and not args.dry_run:
            client.clear_prefix("spam-filter.rule")
            client.clear_prefix("spam-filter.list.scores")
            print("Cleared existing spam-filter rules and scores.")

        all_operations = operations.copy()
        if score_values:
            all_operations.append(
                {
                    "type": "insert",
                    "prefix": "spam-filter.list.scores",
                    "values": score_values,
                    "assertEmpty": False,
                }
            )

        if args.dry_run:
            print(f"Dry-run: would submit {len(all_operations)} operations.")
        else:
            client.apply(all_operations)
            print(f"Imported {len(operations)} rules and {len(score_values)} scores.")
        performed_action = True

    if not performed_action:
        parser.error("No action selected. Use --list, --export, or --import-file.")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
