#!/usr/bin/env python3
"""
Stalwart Spam Filter Training Tool

Train Stalwart's Bayes spam filter with email messages from files or directories.
Supports both global and per-account training.

Author: Jim Dunphy
License: MIT
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List
import base64
import getpass
import mailbox

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: 'requests' library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


class StalwartSpamTrainer:
    """Handle spam/ham training for Stalwart mail server."""

    def __init__(self, server: str, token: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 verbose: bool = False):
        self.server = server.rstrip('/')
        self.token = token
        self.username = username
        self.password = password
        self.verbose = verbose
        self.session = requests.Session()

        # Set up authentication
        if self.token:
            self.session.headers['Authorization'] = f'Bearer {self.token}'
            if self.verbose:
                print(f"Using API token authentication", file=sys.stderr)
        elif self.username and self.password:
            # Basic auth
            auth_str = base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
            self.session.headers['Authorization'] = f'Basic {auth_str}'
            if self.verbose:
                print(f"Using basic authentication for user: {self.username}", file=sys.stderr)

        self.session.headers['Accept'] = 'application/json'

    def train_message_bytes(self, message_data: bytes, train_type: str,
                           account_id: Optional[str] = None, source: str = "") -> Tuple[bool, str]:
        """
        Train spam filter with message bytes.

        Args:
            message_data: Email message as bytes
            train_type: 'spam' or 'ham'
            account_id: Optional account ID for per-user training
            source: Optional source description (for error messages)

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        try:
            # Validate it looks like an email (has headers)
            if not self._validate_message(message_data):
                return False, f"Invalid email format (missing headers)"

            # Build endpoint URL
            if account_id:
                url = f"{self.server}/api/spam-filter/train/{train_type}/{account_id}"
            else:
                url = f"{self.server}/api/spam-filter/train/{train_type}"

            if self.verbose:
                print(f"  POST {url}", file=sys.stderr)
                print(f"  Auth: {list(self.session.headers.keys())}", file=sys.stderr)

            # Send training request
            response = self.session.post(
                url,
                data=message_data,
                headers={'Content-Type': 'message/rfc822'},
                timeout=30
            )

            if self.verbose:
                print(f"  Response: {response.status_code}", file=sys.stderr)

            if response.status_code == 200:
                return True, ""
            else:
                try:
                    error_data = response.json()
                    # Try different error field names
                    error_msg = (error_data.get('detail') or
                                error_data.get('error', {}).get('message') or
                                error_data.get('message') or
                                response.text)
                except:
                    error_msg = response.text or f"HTTP {response.status_code}"
                return False, error_msg

        except requests.exceptions.RequestException as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def train_message(self, message_path: Path, train_type: str,
                     account_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Train spam filter with a single message file.

        Args:
            message_path: Path to email message file
            train_type: 'spam' or 'ham'
            account_id: Optional account ID for per-user training

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        try:
            # Read message
            with open(message_path, 'rb') as f:
                message_data = f.read()

            return self.train_message_bytes(message_data, train_type, account_id, str(message_path))

        except FileNotFoundError:
            return False, "File not found"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def _validate_message(self, data: bytes) -> bool:
        """Check if data looks like a valid email message."""
        # Must have at least one header line
        try:
            lines = data.decode('utf-8', errors='ignore').split('\n', 10)
            # Look for header pattern (Name: value)
            for line in lines[:10]:
                if ':' in line and not line.startswith(' ') and not line.startswith('\t'):
                    return True
            return False
        except:
            return False


def find_email_files(path: Path, recursive: bool = False,
                    pattern: str = "*") -> List[Path]:
    """Find email files in path."""
    files = []

    if path.is_file():
        return [path]

    if path.is_dir():
        if recursive:
            for ext in ['*.eml', '*.msg', '*.txt', '*.mbox']:
                files.extend(path.rglob(ext))
            # Also match custom pattern
            if pattern != "*":
                files.extend(path.rglob(pattern))
        else:
            for ext in ['*.eml', '*.msg', '*.txt', '*.mbox']:
                files.extend(path.glob(ext))
            if pattern != "*":
                files.extend(path.glob(pattern))

    # Remove duplicates and sort
    return sorted(set(files))


def get_auth_token() -> Optional[str]:
    """Get authentication token from environment or file."""
    # Try environment variable
    token = os.getenv('STALWART_TOKEN')
    if token:
        return token

    # Try token file
    token_file = Path.home() / '.stalwart-token'
    if token_file.exists():
        try:
            return token_file.read_text().strip()
        except:
            pass

    return None


def get_server_url() -> str:
    """Get server URL from environment or default."""
    return os.getenv('STALWART_SERVER', 'http://localhost:8080')


def main():
    parser = argparse.ArgumentParser(
        description='Train Stalwart spam filter with email messages',
        epilog="""
Examples:
  # Train single message as spam
  %(prog)s --type spam spam_message.eml

  # Train directory as ham for specific user
  %(prog)s --type ham --account user@example.com ham_folder/

  # Train with custom server and token
  %(prog)s --type spam --server https://mail.example.org --token YOUR_TOKEN spam/

  # Recursive directory scan
  %(prog)s --type spam --recursive /var/mail/spam/

Environment Variables:
  STALWART_SERVER    Server URL (default: http://localhost:8080)
  STALWART_TOKEN     API authentication token

Token File:
  ~/.stalwart-token  API token can also be stored here
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'path',
        type=Path,
        nargs='?',
        help='Path to email file or directory'
    )

    parser.add_argument(
        '--type',
        choices=['spam', 'ham'],
        help='Training type: spam (unwanted) or ham (legitimate)'
    )

    parser.add_argument(
        '--account',
        help='Account ID for per-user training (email address or username)'
    )

    parser.add_argument(
        '--server',
        default=get_server_url(),
        help='Stalwart server URL (default: $STALWART_SERVER or http://localhost:8080)'
    )

    parser.add_argument(
        '--token',
        default=get_auth_token(),
        help='API token (default: $STALWART_TOKEN or ~/.stalwart-token)'
    )

    parser.add_argument(
        '--username',
        help='Username for basic authentication (if no token)'
    )

    parser.add_argument(
        '--password',
        help='Password for basic authentication (if no token)'
    )

    parser.add_argument(
        '--recursive',
        action='store_true',
        help='Recursively scan directories'
    )

    parser.add_argument(
        '--pattern',
        default='*',
        help='File pattern to match (e.g., "*.eml")'
    )

    parser.add_argument(
        '--fail-fast',
        action='store_true',
        help='Stop on first error (default: continue and report)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without training'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    parser.add_argument(
        '--test-message',
        type=Path,
        help='Test spam classification on a message (shows score and rules)'
    )

    parser.add_argument(
        '--count',
        type=int,
        metavar='N',
        help='Limit training to first N messages (useful for testing or limiting load)'
    )

    parser.add_argument(
        '--show-count',
        action='store_true',
        help='Show message counts without training (no authentication needed)'
    )

    parser.add_argument(
        '--purge-first',
        action='store_true',
        help='Purge existing Bayes model before training (use to reset corrupted model)'
    )

    args = parser.parse_args()

    # Handle test-message mode
    if args.test_message:
        if not args.test_message.exists():
            print(f"Error: Test message file does not exist: {args.test_message}", file=sys.stderr)
            sys.exit(1)

        # Create session for API call
        session = requests.Session()
        if args.token:
            session.headers['Authorization'] = f'Bearer {args.token}'
        elif args.username and args.password:
            auth_str = base64.b64encode(f'{args.username}:{args.password}'.encode()).decode()
            session.headers['Authorization'] = f'Basic {auth_str}'
        else:
            print("Error: Authentication required (--token or --username/--password)", file=sys.stderr)
            sys.exit(1)

        session.headers['Accept'] = 'application/json'

        # Read message
        try:
            with open(args.test_message, 'rb') as f:
                message_data = f.read()
        except Exception as e:
            print(f"Error reading message: {e}", file=sys.stderr)
            sys.exit(1)

        # Parse message to extract envelope info
        try:
            from email import message_from_bytes
            parsed = message_from_bytes(message_data)

            # Extract sender info
            from_header = parsed.get('From', 'sender@example.com')
            # Simple email extraction
            if '<' in from_header and '>' in from_header:
                env_from = from_header.split('<')[1].split('>')[0]
            else:
                env_from = from_header.strip()

            # Extract recipient
            to_header = parsed.get('To', 'recipient@example.com')
            if '<' in to_header and '>' in to_header:
                env_to = to_header.split('<')[1].split('>')[0]
            else:
                env_to = to_header.strip()

            # Get domain from sender
            if '@' in env_from:
                ehlo_domain = env_from.split('@')[1]
            else:
                ehlo_domain = 'localhost'

        except:
            env_from = "sender@example.com"
            env_to = "recipient@example.com"
            ehlo_domain = "localhost"

        # Build classify request - API expects JSON body with message and envelope info
        # See: crates/http/src/management/spam.rs SpamClassifyRequest struct
        classify_request = {
            "message": message_data.decode('utf-8', errors='replace'),
            "remoteIp": "203.0.113.1",  # Use example IP (RFC 5737)
            "ehloDomain": ehlo_domain,
            "envFrom": env_from,
            "envFromFlags": 0,
            "envRcptTo": [env_to],
            "isTls": True  # Assume TLS
        }

        # Add authenticated_as if account specified
        if args.account:
            classify_request["authenticatedAs"] = args.account

        classify_url = f"{args.server}/api/spam-filter/classify"

        print(f"Testing message: {args.test_message}")
        print(f"Endpoint: {classify_url}")
        if args.account:
            print(f"Account: {args.account}")
        print("")

        try:
            response = session.post(
                classify_url,
                json=classify_request,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                data = result.get('data', {})
                score = data.get('score', 0)
                tags = data.get('tags', {})

                print("=" * 70)
                print(f"SPAM SCORE: {score:.2f}")
                print("=" * 70)
                print("")

                if tags:
                    print("TRIGGERED RULES:")
                    print("-" * 70)
                    # Sort by score descending
                    sorted_tags = sorted(tags.items(), key=lambda x: x[1].get('value', 0), reverse=True)
                    for tag_name, tag_data in sorted_tags:
                        tag_score = tag_data.get('value', 0)
                        tag_action = tag_data.get('action', 'add_header')
                        print(f"  {tag_name:40s} {tag_score:8.2f}  [{tag_action}]")
                    print("")
                else:
                    print("No rules triggered")
                    print("")

                # Show interpretation
                print("INTERPRETATION:")
                if score < 5.0:
                    print("  ✓ HAM (legitimate email)")
                elif score < 10.0:
                    print("  ⚠ POSSIBLE SPAM (borderline)")
                else:
                    print("  ✗ SPAM (likely unwanted)")

                sys.exit(0)
            else:
                print(f"Error: HTTP {response.status_code}", file=sys.stderr)
                print(response.text, file=sys.stderr)
                sys.exit(1)

        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}", file=sys.stderr)
            sys.exit(1)

    # Handle show-count mode
    if args.show_count:
        if not args.path:
            print("Error: path argument is required for --show-count", file=sys.stderr)
            parser.print_help(sys.stderr)
            sys.exit(1)

        if not args.path.exists():
            print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
            sys.exit(1)

        # Find files
        files = find_email_files(args.path, args.recursive, args.pattern)

        if not files:
            print(f"No email files found in {args.path}", file=sys.stderr)
            sys.exit(1)

        # Separate mbox and regular files
        mbox_files = [f for f in files if f.suffix == '.mbox']
        regular_files = [f for f in files if f.suffix != '.mbox']

        print("=" * 70)
        print("MESSAGE COUNT")
        print("=" * 70)
        print(f"Path: {args.path}")
        if args.recursive:
            print("Mode: Recursive")
        if args.pattern != '*':
            print(f"Pattern: {args.pattern}")
        print("")

        # Count individual files
        if regular_files:
            print(f"Individual email files: {len(regular_files)}")
            if args.verbose:
                for f in regular_files[:10]:
                    print(f"  {f}")
                if len(regular_files) > 10:
                    print(f"  ... and {len(regular_files) - 10} more")
            print("")

        # Count mbox files and messages
        if mbox_files:
            total_mbox_messages = 0
            print(f"Mbox files: {len(mbox_files)}")
            for mbox_file in mbox_files:
                try:
                    mbox = mailbox.mbox(str(mbox_file))
                    msg_count = len(mbox)
                    total_mbox_messages += msg_count
                    file_size = mbox_file.stat().st_size
                    print(f"  {mbox_file.name:40s} {msg_count:6,} messages  ({file_size:,} bytes)")
                except Exception as e:
                    print(f"  {mbox_file.name:40s} ERROR: {e}")

            print("")
            print(f"Total messages in mbox files: {total_mbox_messages:,}")
            print("")

        # Grand total
        grand_total = len(regular_files) + sum(
            len(mailbox.mbox(str(m))) for m in mbox_files
            if m.exists() and m.suffix == '.mbox'
        )
        print("=" * 70)
        print(f"GRAND TOTAL: {grand_total:,} messages")
        print("=" * 70)
        sys.exit(0)

    # Validate required arguments for training mode
    if not args.path:
        print("Error: path argument is required", file=sys.stderr)
        parser.print_help(sys.stderr)
        sys.exit(1)

    if not args.type:
        print("Error: --type argument is required", file=sys.stderr)
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Validate path exists
    if not args.path.exists():
        print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(1)

    # Check/prompt for authentication
    if not args.token:
        # No token, need username/password
        # Prompt for missing credentials
        if not args.username:
            if args.password:
                # Have password but no username - weird, but prompt for username
                print("Password provided but username missing.", file=sys.stderr)
            else:
                print("No authentication credentials found.", file=sys.stderr)
            print("", file=sys.stderr)
            try:
                args.username = input("Username: ")
            except (KeyboardInterrupt, EOFError):
                print("\n\nAuthentication cancelled", file=sys.stderr)
                sys.exit(1)

        if not args.password:
            try:
                args.password = getpass.getpass("Password: ")
            except (KeyboardInterrupt, EOFError):
                print("\n\nAuthentication cancelled", file=sys.stderr)
                sys.exit(1)

        if not args.username or not args.password:
            print("\nError: Username and password are required", file=sys.stderr)
            sys.exit(1)

        print("", file=sys.stderr)

    # Find files to process
    files = find_email_files(args.path, args.recursive, args.pattern)

    if not files:
        print(f"Error: No email files found in {args.path}", file=sys.stderr)
        sys.exit(1)

    # Separate mbox files from regular files and count messages
    mbox_files = [f for f in files if f.suffix == '.mbox']
    regular_files = [f for f in files if f.suffix != '.mbox']

    # Count messages in mbox files
    total_mbox_messages = 0
    for mbox_file in mbox_files:
        try:
            mbox = mailbox.mbox(str(mbox_file))
            total_mbox_messages += len(mbox)
        except Exception:
            # If we can't read it now, we'll report error later
            pass

    # Print summary
    if regular_files and mbox_files:
        print(f"Found {len(regular_files)} individual file(s) + {len(mbox_files)} mbox file(s) ({total_mbox_messages} messages) to train as {args.type.upper()}", file=sys.stderr)
    elif mbox_files:
        print(f"Found {len(mbox_files)} mbox file(s) containing {total_mbox_messages} message(s) to train as {args.type.upper()}", file=sys.stderr)
    else:
        print(f"Found {len(regular_files)} file(s) to train as {args.type.upper()}", file=sys.stderr)

    if args.account:
        print(f"Training for account: {args.account}", file=sys.stderr)
    if args.dry_run:
        print("DRY RUN - No actual training will occur", file=sys.stderr)
    print("", file=sys.stderr)

    # Create trainer (needed for dry-run to show auth headers)
    trainer = StalwartSpamTrainer(
        args.server,
        args.token,
        args.username,
        args.password,
        args.verbose
    )

    # Handle purge-first option
    if args.purge_first:
        if args.account:
            purge_url = f"{args.server}/api/store/purge/in-memory/default/bayes-account/{args.account}"
            model_type = f"account '{args.account}'"
        else:
            purge_url = f"{args.server}/api/store/purge/in-memory/default/bayes-global"
            model_type = "global"

        print(f"Purging Bayes model for {model_type}...", file=sys.stderr)

        try:
            response = trainer.session.get(purge_url, timeout=30)

            if response.status_code == 200:
                print(f"✓ Successfully purged {model_type} Bayes model", file=sys.stderr)
                print("", file=sys.stderr)
            else:
                print(f"⚠ Warning: Purge returned HTTP {response.status_code}", file=sys.stderr)
                print(f"  Response: {response.text}", file=sys.stderr)
                print("  Continuing with training anyway...", file=sys.stderr)
                print("", file=sys.stderr)
        except Exception as e:
            print(f"⚠ Warning: Failed to purge model: {e}", file=sys.stderr)
            print("  Continuing with training anyway...", file=sys.stderr)
            print("", file=sys.stderr)

    if args.dry_run:
        # Build endpoint URL
        if args.account:
            endpoint = f"{args.server}/api/spam-filter/train/{args.type}/{args.account}"
        else:
            endpoint = f"{args.server}/api/spam-filter/train/{args.type}"

        # Show authentication
        auth_header = trainer.session.headers.get('Authorization', 'None')
        if auth_header.startswith('Bearer '):
            auth_display = f"Bearer {auth_header[7:15]}...{auth_header[-8:]}"
        elif auth_header.startswith('Basic '):
            auth_display = f"Basic {auth_header[6:14]}...{auth_header[-8:]}"
        else:
            auth_display = auth_header

        print("=" * 70)
        print("API ENDPOINT DETAILS")
        print("=" * 70)
        print(f"HTTP Method:  POST")
        print(f"URL:          {endpoint}")
        print(f"Content-Type: message/rfc822")
        print(f"Accept:       application/json")
        print(f"Authorization: {auth_display}")
        print("")

        # Show regular files
        if regular_files:
            print("=" * 70)
            print(f"INDIVIDUAL EMAIL FILES ({len(regular_files)})")
            print("=" * 70)
            for f in regular_files[:5]:  # Show first 5
                try:
                    file_size = f.stat().st_size
                    with open(f, 'rb') as fh:
                        preview = fh.read(300).decode('utf-8', errors='ignore')
                        lines = preview.split('\n')[:5]
                    print(f"\nFile: {f}")
                    print(f"Size: {file_size:,} bytes")
                    print(f"Preview:")
                    for line in lines:
                        print(f"  {line[:75]}")
                    print(f"  ...")
                except Exception as e:
                    print(f"\nFile: {f}")
                    print(f"  Error reading: {e}")

            if len(regular_files) > 5:
                print(f"\n... and {len(regular_files) - 5} more files")

        # Show mbox files
        if mbox_files:
            print("")
            print("=" * 70)
            print(f"MBOX FILES ({len(mbox_files)})")
            print("=" * 70)
            for mbox_file in mbox_files:
                try:
                    mbox = mailbox.mbox(str(mbox_file))
                    mbox_size = len(mbox)
                    file_size = mbox_file.stat().st_size

                    print(f"\nMbox: {mbox_file}")
                    print(f"File size: {file_size:,} bytes")
                    print(f"Messages: {mbox_size}")

                    # Show first message preview
                    if mbox_size > 0:
                        first_msg = mbox[0]
                        msg_bytes = first_msg.as_bytes()
                        preview = msg_bytes[:300].decode('utf-8', errors='ignore')
                        lines = preview.split('\n')[:5]
                        print(f"First message preview:")
                        for line in lines:
                            print(f"  {line[:75]}")
                        print(f"  ...")
                        print(f"(Each of {mbox_size} messages will be sent individually)")
                except Exception as e:
                    print(f"\nMbox: {mbox_file}")
                    print(f"  Error reading: {e}")

        print("")
        print("=" * 70)
        print(f"Total: {sum(1 for f in regular_files) + sum(len(mailbox.mbox(str(m))) for m in mbox_files if m.exists())} messages would be trained")
        print("=" * 70)
        sys.exit(0)

    # Process files
    success_count = 0
    error_count = 0
    errors = []
    total_messages = 0

    # Check if we should limit the number of messages
    message_limit = args.count if args.count else None
    messages_processed = 0

    # Process regular files
    if regular_files:
        if HAS_TQDM and not args.verbose:
            file_iter = tqdm(regular_files, desc=f"Training {args.type}", unit="msg")
        else:
            file_iter = regular_files

        for file_path in file_iter:
            # Check message limit
            if message_limit and messages_processed >= message_limit:
                if args.verbose or not HAS_TQDM:
                    print(f"\nReached message limit of {message_limit}", file=sys.stderr)
                break

            if args.verbose:
                print(f"Processing: {file_path}", file=sys.stderr)

            success, error_msg = trainer.train_message(file_path, args.type, args.account)
            total_messages += 1
            messages_processed += 1

            if success:
                success_count += 1
                if args.verbose:
                    print(f"  ✓ Success", file=sys.stderr)
            else:
                error_count += 1
                errors.append((file_path, error_msg))
                if args.verbose or not HAS_TQDM:
                    print(f"  ✗ Failed: {error_msg}", file=sys.stderr)

                if args.fail_fast:
                    print(f"\nStopping on first error (--fail-fast)", file=sys.stderr)
                    break

    # Process mbox files
    for mbox_file in mbox_files:
        # Check if we've hit the limit already
        if message_limit and messages_processed >= message_limit:
            if args.verbose:
                print(f"\nReached message limit of {message_limit}", file=sys.stderr)
            break

        if args.verbose:
            print(f"Processing mbox file: {mbox_file}", file=sys.stderr)
        else:
            print(f"Processing mbox: {mbox_file}", file=sys.stderr)

        try:
            mbox = mailbox.mbox(str(mbox_file))
            mbox_size = len(mbox)

            if args.verbose:
                print(f"  Found {mbox_size} messages in mbox", file=sys.stderr)

            # If limited, adjust mbox size display
            if message_limit:
                remaining = message_limit - messages_processed
                if remaining < mbox_size:
                    if args.verbose or not HAS_TQDM:
                        print(f"  Will process {remaining} of {mbox_size} messages (limit)", file=sys.stderr)
                    mbox_size = remaining

            # Create progress bar for mbox
            if HAS_TQDM and not args.verbose:
                msg_iter = tqdm(mbox, desc=f"  Training from {mbox_file.name}",
                               unit="msg", total=mbox_size, leave=False)
            else:
                msg_iter = mbox
                if not args.verbose:
                    print(f"  Processing {mbox_size} messages...", file=sys.stderr)

            for idx, message in enumerate(msg_iter, 1):
                # Check message limit
                if message_limit and messages_processed >= message_limit:
                    if args.verbose:
                        print(f"  Reached message limit of {message_limit}", file=sys.stderr)
                    break

                try:
                    message_bytes = message.as_bytes()
                    success, error_msg = trainer.train_message_bytes(
                        message_bytes, args.type, args.account,
                        f"{mbox_file}:msg#{idx}"
                    )
                    total_messages += 1
                    messages_processed += 1

                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append((f"{mbox_file}:msg#{idx}", error_msg))
                        if args.verbose:
                            print(f"  ✗ Message #{idx} failed: {error_msg}", file=sys.stderr)

                        if args.fail_fast:
                            print(f"\nStopping on first error (--fail-fast)", file=sys.stderr)
                            break
                except Exception as e:
                    error_count += 1
                    total_messages += 1
                    messages_processed += 1
                    errors.append((f"{mbox_file}:msg#{idx}", str(e)))
                    if args.verbose:
                        print(f"  ✗ Message #{idx} error: {e}", file=sys.stderr)
                    if args.fail_fast:
                        break

        except Exception as e:
            print(f"  ✗ Error reading mbox file: {e}", file=sys.stderr)
            errors.append((mbox_file, f"Failed to read mbox: {e}"))
            if args.fail_fast:
                break

    # Print summary
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Training Summary", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Type:       {args.type.upper()}", file=sys.stderr)
    if mbox_files:
        print(f"Files:      {len(regular_files)} individual, {len(mbox_files)} mbox", file=sys.stderr)
    print(f"Total:      {total_messages} messages", file=sys.stderr)
    if message_limit:
        print(f"Limit:      {message_limit} (stopped early)", file=sys.stderr)
    print(f"Successful: {success_count}", file=sys.stderr)
    print(f"Failed:     {error_count}", file=sys.stderr)

    if errors and not args.verbose:
        print("", file=sys.stderr)
        print("Errors:", file=sys.stderr)
        for file_path, error_msg in errors[:10]:  # Show first 10 errors
            print(f"  {file_path}: {error_msg}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors", file=sys.stderr)

    # Exit with error code if any failures
    sys.exit(0 if error_count == 0 else 1)


if __name__ == '__main__':
    main()
