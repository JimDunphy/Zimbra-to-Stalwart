#!/usr/bin/env python3
"""Upload and activate a Sieve script over ManageSieve."""

from __future__ import annotations

import argparse
import base64
import pathlib
import socket
import ssl
import sys
from typing import Iterable, Optional, Tuple, List


class ManageSieveError(RuntimeError):
    """Raised when the server returns a failure status."""


class ManageSieveClient:
    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool,
        starttls: bool,
        insecure: bool,
        timeout: float,
    ) -> None:
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.starttls = starttls
        self.insecure = insecure
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[socket.SocketIO] = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.reader = self.sock.makefile("rb")
        if self.use_tls and not self.starttls:
            self._wrap_tls()
        self._expect_ok()  # greeting
        if self.starttls:
            self._send_line("STARTTLS")
            self._expect_ok()
            self._wrap_tls()

    def close(self) -> None:
        try:
            self._send_line("LOGOUT")
            self._expect_ok()
        except Exception:
            pass
        if self.reader:
            self.reader.close()
        if self.sock:
            self.sock.close()

    def _wrap_tls(self) -> None:
        if not self.sock:
            raise ManageSieveError("Not connected")
        ctx = ssl.create_default_context()
        if self.insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.sock = ctx.wrap_socket(self.sock, server_hostname=self.host)
        self.reader = self.sock.makefile("rb")

    def _send_line(self, line: str) -> None:
        if not self.sock:
            raise ManageSieveError("Not connected")
        self.sock.sendall((line + "\r\n").encode("utf-8"))

    def _read_response(self) -> Tuple[str, List[str]]:
        if not self.reader:
            raise ManageSieveError("Not connected")
        data: List[str] = []
        while True:
            line = self.reader.readline()
            if not line:
                raise ManageSieveError("Connection closed")
            decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if decoded.startswith(("OK", "NO", "BYE")):
                if decoded.startswith(("NO", "BYE")):
                    raise ManageSieveError(decoded)
                return decoded, data
            data.append(decoded)

    def _expect_ok(self) -> str:
        status, _ = self._read_response()
        return status

    def authenticate_plain(self, username: str, password: str) -> None:
        blob = base64.b64encode(f"\x00{username}\x00{password}".encode("utf-8")).decode("ascii")
        self._send_line('AUTHENTICATE "PLAIN"')
        if not self.reader:
            raise ManageSieveError("Not connected")
        challenge = self.reader.readline().decode("utf-8", errors="replace").strip()
        if not challenge.startswith("+"):
            raise ManageSieveError(challenge or "AUTHENTICATE failed")
        self._send_line(blob)
        self._expect_ok()

    def put_script(self, name: str, body: bytes) -> None:
        literal = f'PUTSCRIPT "{name}" {{{len(body)}+}}'
        self._send_line(literal)
        assert self.sock
        self.sock.sendall(body)
        if not body.endswith(b"\n"):
            self.sock.sendall(b"\n")
        self.sock.sendall(b"\r\n")
        self._expect_ok()

    def set_active(self, name: str) -> None:
        self._send_line(f'SETACTIVE "{name}"')
        self._expect_ok()

    def delete_script(self, name: str) -> None:
        self._send_line(f'DELETESCRIPT "{name}"')
        self._expect_ok()

    def list_scripts(self) -> List[Tuple[str, bool]]:
        self._send_line("LISTSCRIPTS")
        _, lines = self._read_response()
        results: List[Tuple[str, bool]] = []
        for line in lines:
            label = line.strip()
            active = label.endswith(" ACTIVE")
            if active:
                label = label[:-7].rstrip()
            results.append((label.strip('"'), active))
        return results


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage Sieve scripts via ManageSieve.")
    parser.add_argument("--host", default="localhost", help="ManageSieve host (default: localhost)")
    parser.add_argument("--port", type=int, default=4190, help="ManageSieve port (default: 4190)")
    parser.add_argument("--username", required=True, help="Account username")
    parser.add_argument("--password", required=True, help="Account password")
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--import", dest="do_import", action="store_true", help="Upload (and optionally activate) a script")
    action_group.add_argument("--list", dest="do_list", action="store_true", help="List scripts on the server")
    action_group.add_argument("--delete", metavar="NAME", dest="delete_name", help="Delete the named script")
    parser.add_argument("--script-file", type=pathlib.Path, help="Local Sieve script to upload (required with --import)")
    parser.add_argument("--script-name", default="uploaded", help="Remote script name (default: uploaded)")
    parser.add_argument("--no-activate", action="store_true", help="Do not set the uploaded script active")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without contacting the server (import only)")
    parser.add_argument("--plaintext", action="store_true", help="Disable TLS (only for trusted dev labs)")
    parser.add_argument("--starttls", action="store_true", help="Use STARTTLS instead of implicit TLS")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS certificate validation")
    parser.add_argument("--timeout", type=float, default=10.0, help="Network timeout in seconds")
    return parser.parse_args(list(argv) if argv is not None else None)


def load_script(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    return data.replace(b"\r\n", b"\n")


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    if args.dry_run and not args.do_import:
        print("--dry-run is only valid with --import", file=sys.stderr)
        return 2
    if args.do_import and not args.script_file:
        print("--script-file is required when using --import", file=sys.stderr)
        return 2
    script_body = load_script(args.script_file) if args.script_file else b""
    client = ManageSieveClient(
        host=args.host,
        port=args.port,
        use_tls=not args.plaintext,
        starttls=args.starttls,
        insecure=args.insecure,
        timeout=args.timeout,
    )
    if args.do_import and args.dry_run:
        print(f"[dry-run] Would upload {args.script_file} as '{args.script_name}' to {args.host}:{args.port}")
        if args.no_activate:
            print("[dry-run] Script would remain inactive after upload")
        return 0
    try:
        client.connect()
        client.authenticate_plain(args.username, args.password)
        if args.do_list:
            scripts = client.list_scripts()
            if not scripts:
                print("No scripts found.")
            else:
                for name, active in scripts:
                    marker = "*" if active else " "
                    print(f"{marker} {name}")
            return 0
        if args.delete_name:
            client.delete_script(args.delete_name)
            print(f"Deleted script '{args.delete_name}' from {args.host}:{args.port}")
            return 0
        if args.do_import:
            client.put_script(args.script_name, script_body)
            if not args.no_activate:
                client.set_active(args.script_name)
            msg = f"Uploaded {args.script_file} as '{args.script_name}' to {args.host}:{args.port}"
            if args.no_activate:
                msg += " (not activated)"
            print(msg)
            return 0
        print("No action specified.", file=sys.stderr)
        return 2
    except ManageSieveError as exc:
        print(f"ManageSieve error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ssl.SSLError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
