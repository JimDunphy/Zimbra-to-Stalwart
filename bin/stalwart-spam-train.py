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
        help='Path to email file or directory'
    )

    parser.add_argument(
        '--type',
        choices=['spam', 'ham'],
        required=True,
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

    args = parser.parse_args()

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

    print(f"Found {len(files)} file(s) to train as {args.type.upper()}", file=sys.stderr)
    if args.account:
        print(f"Training for account: {args.account}", file=sys.stderr)
    if args.dry_run:
        print("DRY RUN - No actual training will occur", file=sys.stderr)
    print("", file=sys.stderr)

    if args.dry_run:
        for f in files:
            print(f"Would train: {f}")
        sys.exit(0)

    # Create trainer
    trainer = StalwartSpamTrainer(
        args.server,
        args.token,
        args.username,
        args.password,
        args.verbose
    )

    # Process files
    success_count = 0
    error_count = 0
    errors = []
    total_messages = 0

    # Separate mbox files from regular files
    mbox_files = [f for f in files if f.suffix == '.mbox']
    regular_files = [f for f in files if f.suffix != '.mbox']

    # Process regular files
    if regular_files:
        if HAS_TQDM and not args.verbose:
            file_iter = tqdm(regular_files, desc=f"Training {args.type}", unit="msg")
        else:
            file_iter = regular_files

        for file_path in file_iter:
            if args.verbose:
                print(f"Processing: {file_path}", file=sys.stderr)

            success, error_msg = trainer.train_message(file_path, args.type, args.account)
            total_messages += 1

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
        if args.verbose:
            print(f"Processing mbox file: {mbox_file}", file=sys.stderr)
        else:
            print(f"Processing mbox: {mbox_file}", file=sys.stderr)

        try:
            mbox = mailbox.mbox(str(mbox_file))
            mbox_size = len(mbox)

            if args.verbose:
                print(f"  Found {mbox_size} messages in mbox", file=sys.stderr)

            # Create progress bar for mbox
            if HAS_TQDM and not args.verbose:
                msg_iter = tqdm(mbox, desc=f"  Training from {mbox_file.name}",
                               unit="msg", total=mbox_size, leave=False)
            else:
                msg_iter = mbox
                if not args.verbose:
                    print(f"  Processing {mbox_size} messages...", file=sys.stderr)

            for idx, message in enumerate(msg_iter, 1):
                try:
                    message_bytes = message.as_bytes()
                    success, error_msg = trainer.train_message_bytes(
                        message_bytes, args.type, args.account,
                        f"{mbox_file}:msg#{idx}"
                    )
                    total_messages += 1

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
