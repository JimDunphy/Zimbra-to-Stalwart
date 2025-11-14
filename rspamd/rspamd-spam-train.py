#!/usr/bin/env python3
"""
rspamd-spam-train.py - Train Rspamd Bayes classifier from Stalwart IMAP folders

This script connects to Stalwart IMAP server, retrieves messages from designated
spam and ham folders, and trains the Rspamd Bayes classifier via its HTTP API.

Usage:
    ./rspamd-spam-train.py --train
    ./rspamd-spam-train.py --stats
    ./rspamd-spam-train.py --reset

Author: Based on stalwart-spam-train.py by Jim Dunphy
License: MIT
"""

import imaplib
import email
import requests
import argparse
import sys
import json
import os
from datetime import datetime
from email import policy
from pathlib import Path

# Configuration
CONFIG = {
    'imap_host': 'localhost',
    'imap_port': 993,
    'imap_user': 'user@example.com',  # UPDATE THIS
    'imap_password': None,  # Will prompt or read from env
    'rspamd_url': 'http://localhost:11334',
    'rspamd_password': None,  # Optional, for stats
    'spam_folder': 'Junk',
    'ham_folder': 'INBOX',
    'max_messages': 1000,  # Max messages to train per run
    'state_file': '/tmp/rspamd-train-state.json',
    'use_ssl': True,
}

class RspamdTrainer:
    def __init__(self, config):
        self.config = config
        self.state = self.load_state()
        self.trained_count = {'spam': 0, 'ham': 0}
        
    def load_state(self):
        """Load state of previously trained messages"""
        if os.path.exists(self.config['state_file']):
            with open(self.config['state_file'], 'r') as f:
                return json.load(f)
        return {'spam_uids': [], 'ham_uids': [], 'last_run': None}
    
    def save_state(self):
        """Save state of trained messages"""
        self.state['last_run'] = datetime.now().isoformat()
        with open(self.config['state_file'], 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def connect_imap(self):
        """Connect to IMAP server"""
        try:
            if self.config['use_ssl']:
                imap = imaplib.IMAP4_SSL(self.config['imap_host'], self.config['imap_port'])
            else:
                imap = imaplib.IMAP4(self.config['imap_host'], self.config['imap_port'])
            
            password = self.config['imap_password'] or os.getenv('IMAP_PASSWORD')
            if not password:
                from getpass import getpass
                password = getpass(f"IMAP Password for {self.config['imap_user']}: ")
            
            imap.login(self.config['imap_user'], password)
            print(f"✓ Connected to IMAP server as {self.config['imap_user']}")
            return imap
        except Exception as e:
            print(f"✗ IMAP connection failed: {e}")
            sys.exit(1)
    
    def get_message_uids(self, imap, folder):
        """Get all message UIDs from a folder"""
        try:
            status, data = imap.select(folder, readonly=True)
            if status != 'OK':
                print(f"✗ Could not select folder: {folder}")
                return []
            
            status, data = imap.uid('search', None, 'ALL')
            if status != 'OK':
                return []
            
            uids = data[0].split()
            return [uid.decode() for uid in uids]
        except Exception as e:
            print(f"✗ Error getting UIDs from {folder}: {e}")
            return []
    
    def fetch_message(self, imap, uid):
        """Fetch a message by UID"""
        try:
            status, data = imap.uid('fetch', uid, '(RFC822)')
            if status != 'OK':
                return None
            return data[0][1]
        except Exception as e:
            print(f"✗ Error fetching message {uid}: {e}")
            return None
    
    def train_rspamd(self, message_data, is_spam):
        """Send message to rspamd for training"""
        endpoint = 'learnspam' if is_spam else 'learnham'
        url = f"{self.config['rspamd_url']}/{endpoint}"
        
        try:
            response = requests.post(
                url,
                data=message_data,
                headers={'Content-Type': 'message/rfc822'},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success', False):
                    return True
                else:
                    print(f"  Warning: Training failed - {result.get('error', 'unknown error')}")
                    return False
            else:
                print(f"  Warning: HTTP {response.status_code} - {response.text[:100]}")
                return False
        except Exception as e:
            print(f"  Error training message: {e}")
            return False
    
    def train_folder(self, imap, folder, is_spam):
        """Train all new messages from a folder"""
        msg_type = "spam" if is_spam else "ham"
        state_key = f"{msg_type}_uids"
        
        print(f"\n{'='*60}")
        print(f"Training {msg_type.upper()} from folder: {folder}")
        print(f"{'='*60}")
        
        # Get all UIDs in folder
        all_uids = self.get_message_uids(imap, folder)
        if not all_uids:
            print(f"✗ No messages found in {folder}")
            return
        
        # Filter out already trained messages
        trained_uids = set(self.state.get(state_key, []))
        new_uids = [uid for uid in all_uids if uid not in trained_uids]
        
        if not new_uids:
            print(f"✓ No new messages to train (all {len(all_uids)} already trained)")
            return
        
        print(f"Found {len(new_uids)} new messages to train (out of {len(all_uids)} total)")
        
        # Limit messages if configured
        if len(new_uids) > self.config['max_messages']:
            print(f"Limiting to {self.config['max_messages']} messages")
            new_uids = new_uids[:self.config['max_messages']]
        
        # Select folder for fetching
        imap.select(folder, readonly=True)
        
        # Train each message
        success_count = 0
        for i, uid in enumerate(new_uids, 1):
            msg_data = self.fetch_message(imap, uid)
            if not msg_data:
                continue
            
            if self.train_rspamd(msg_data, is_spam):
                success_count += 1
                trained_uids.add(uid)
                
                # Progress indicator
                if i % 10 == 0 or i == len(new_uids):
                    print(f"  Progress: {i}/{len(new_uids)} messages trained")
        
        # Update state
        self.state[state_key] = list(trained_uids)
        self.trained_count[msg_type] = success_count
        
        print(f"✓ Successfully trained {success_count}/{len(new_uids)} {msg_type} messages")
    
    def get_rspamd_stats(self):
        """Get Bayes statistics from rspamd"""
        url = f"{self.config['rspamd_url']}/stat"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Warning: Could not get rspamd stats: {e}")
        return None
    
    def print_stats(self):
        """Print training statistics"""
        print(f"\n{'='*60}")
        print("Rspamd Bayes Training Statistics")
        print(f"{'='*60}")
        
        stats = self.get_rspamd_stats()
        if stats:
            # Look for bayes statistics in the response
            # The structure varies, but typically under 'statfiles' or similar
            print("Rspamd Stats:")
            print(json.dumps(stats, indent=2))
        
        print("\nLocal Training State:")
        print(f"  Spam messages trained: {len(self.state.get('spam_uids', []))}")
        print(f"  Ham messages trained: {len(self.state.get('ham_uids', []))}")
        print(f"  Last training run: {self.state.get('last_run', 'Never')}")
        
        if len(self.state.get('spam_uids', [])) < 200 or len(self.state.get('ham_uids', [])) < 200:
            print("\n⚠ Warning: Bayes requires at least 200 spam and 200 ham messages to activate")
            print(f"  Need {max(0, 200 - len(self.state.get('spam_uids', [])))} more spam messages")
            print(f"  Need {max(0, 200 - len(self.state.get('ham_uids', [])))} more ham messages")
    
    def reset_state(self):
        """Reset training state (does not untrain rspamd)"""
        print("⚠ Warning: This will reset the training state file.")
        print("   Messages will be retrained on next run.")
        print("   This does NOT clear rspamd's Bayes database.")
        
        response = input("\nAre you sure? (yes/no): ")
        if response.lower() == 'yes':
            self.state = {'spam_uids': [], 'ham_uids': [], 'last_run': None}
            self.save_state()
            print("✓ State file reset")
        else:
            print("Cancelled")
    
    def train(self):
        """Main training function"""
        print("Rspamd Bayes Training Script")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Connect to IMAP
        imap = self.connect_imap()
        
        try:
            # Train spam
            self.train_folder(imap, self.config['spam_folder'], is_spam=True)
            
            # Train ham
            self.train_folder(imap, self.config['ham_folder'], is_spam=False)
            
            # Save state
            self.save_state()
            
            # Print summary
            print(f"\n{'='*60}")
            print("Training Summary")
            print(f"{'='*60}")
            print(f"Spam messages trained this run: {self.trained_count['spam']}")
            print(f"Ham messages trained this run: {self.trained_count['ham']}")
            print(f"Total spam trained: {len(self.state['spam_uids'])}")
            print(f"Total ham trained: {len(self.state['ham_uids'])}")
            
            if len(self.state['spam_uids']) >= 200 and len(self.state['ham_uids']) >= 200:
                print("\n✓ Bayes classifier has sufficient training data")
            else:
                print(f"\n⚠ Need more training data:")
                print(f"  Spam: {max(0, 200 - len(self.state['spam_uids']))} more needed")
                print(f"  Ham: {max(0, 200 - len(self.state['ham_uids']))} more needed")
            
        finally:
            imap.logout()

def main():
    parser = argparse.ArgumentParser(
        description='Train Rspamd Bayes classifier from Stalwart IMAP folders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --train              Train from new messages
  %(prog)s --stats              Show training statistics
  %(prog)s --reset              Reset training state
  
Configuration:
  Set IMAP_PASSWORD environment variable to avoid password prompt:
    export IMAP_PASSWORD="your_password"
    %(prog)s --train
  
  Or edit the CONFIG dictionary in the script.
        """
    )
    
    parser.add_argument('--train', action='store_true',
                       help='Train Bayes from IMAP folders')
    parser.add_argument('--stats', action='store_true',
                       help='Show training statistics')
    parser.add_argument('--reset', action='store_true',
                       help='Reset training state file')
    parser.add_argument('--spam-folder', default=CONFIG['spam_folder'],
                       help=f"Spam folder name (default: {CONFIG['spam_folder']})")
    parser.add_argument('--ham-folder', default=CONFIG['ham_folder'],
                       help=f"Ham folder name (default: {CONFIG['ham_folder']})")
    parser.add_argument('--max', type=int, default=CONFIG['max_messages'],
                       help=f"Max messages per run (default: {CONFIG['max_messages']})")
    
    args = parser.parse_args()
    
    # Update config from args
    CONFIG['spam_folder'] = args.spam_folder
    CONFIG['ham_folder'] = args.ham_folder
    CONFIG['max_messages'] = args.max
    
    # Create trainer
    trainer = RspamdTrainer(CONFIG)
    
    # Execute command
    if args.train:
        trainer.train()
    elif args.stats:
        trainer.print_stats()
    elif args.reset:
        trainer.reset_state()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
