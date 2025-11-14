# Rspamd Bayes Training Guide

## Overview

This script trains Rspamd's Bayes classifier by connecting to your Stalwart IMAP server and learning from pre-classified messages in your Junk and Inbox folders.

## Features

- ✅ Connects to Stalwart IMAP server
- ✅ Trains from your vetted Junk (spam) and Inbox (ham) folders
- ✅ Tracks which messages have been trained (no duplicates)
- ✅ Can be run multiple times safely
- ✅ Shows progress and statistics
- ✅ Requires minimum 200 spam + 200 ham to activate Bayes

## Prerequisites

```bash
# Install required Python packages
pip3 install requests --break-system-packages

# Or use a virtual environment
python3 -m venv ~/venv-rspamd-train
source ~/venv-rspamd-train/bin/activate
pip install requests
```

## Installation

```bash
# Download the script
cp /path/to/rspamd-spam-train.py ~/rspamd-spam-train.py
chmod +x ~/rspamd-spam-train.py

# Edit configuration
nano ~/rspamd-spam-train.py
# Update these values in the CONFIG dictionary:
#   'imap_user': 'your_email@your_domain.com'
#   'imap_host': 'localhost' (or your Stalwart server)
```

## Configuration

Edit the `CONFIG` dictionary in the script:

```python
CONFIG = {
    'imap_host': 'localhost',          # Stalwart IMAP server
    'imap_port': 993,                   # IMAP SSL port
    'imap_user': 'user@mx.example.com', # Your email address
    'imap_password': None,              # Will prompt or use env var
    'rspamd_url': 'http://localhost:11334',
    'spam_folder': 'Junk',              # Your spam folder
    'ham_folder': 'INBOX',              # Your ham folder
    'max_messages': 1000,               # Max per run
    'state_file': '/tmp/rspamd-train-state.json',
}
```

## Usage

### Initial Training

```bash
# Train from your existing messages
./rspamd-spam-train.py --train

# You'll be prompted for your IMAP password
# Or set it as an environment variable:
export IMAP_PASSWORD="your_password"
./rspamd-spam-train.py --train
```

### Check Statistics

```bash
./rspamd-spam-train.py --stats
```

Shows:
- How many spam messages trained
- How many ham messages trained
- Whether you've reached the 200 minimum threshold
- Last training run timestamp

### Incremental Training

As you classify more messages in Thunderbird:
- Move spam to Junk folder
- Keep ham in Inbox
- Run training script periodically

```bash
./rspamd-spam-train.py --train
```

The script remembers what it already trained, so it only trains new messages.

### Reset State

If you want to retrain everything:

```bash
./rspamd-spam-train.py --reset
```

**Note**: This only resets the script's memory of what was trained. It doesn't clear rspamd's Bayes database.

## Command Line Options

```bash
./rspamd-spam-train.py --help

Options:
  --train              Train from new messages in IMAP folders
  --stats              Show training statistics
  --reset              Reset training state (retrain on next run)
  --spam-folder NAME   Override spam folder name (default: Junk)
  --ham-folder NAME    Override ham folder name (default: INBOX)
  --max N              Max messages to train per run (default: 1000)
```

## Example Workflow

### 1. Initial Setup (First Time)

```bash
# Edit script configuration
nano ~/rspamd-spam-train.py
# Update imap_user to your email

# Make executable
chmod +x ~/rspamd-spam-train.py

# Set password (optional)
export IMAP_PASSWORD="your_password"

# Run initial training
./rspamd-spam-train.py --train
```

Expected output:
```
Rspamd Bayes Training Script
Started at: 2025-11-14 18:30:00
✓ Connected to IMAP server as user@mx.example.com

============================================================
Training SPAM from folder: Junk
============================================================
Found 150 new messages to train (out of 150 total)
  Progress: 10/150 messages trained
  Progress: 20/150 messages trained
  ...
  Progress: 150/150 messages trained
✓ Successfully trained 150/150 spam messages

============================================================
Training HAM from folder: INBOX
============================================================
Found 300 new messages to train (out of 300 total)
  Progress: 10/300 messages trained
  ...
✓ Successfully trained 300/300 ham messages

============================================================
Training Summary
============================================================
Spam messages trained this run: 150
Ham messages trained this run: 300
Total spam trained: 150
Total ham trained: 300

⚠ Need more training data:
  Spam: 50 more needed
  Ham: 0 more needed
```

### 2. Continue Training

```bash
# Move more spam to Junk folder in Thunderbird
# Run training again
./rspamd-spam-train.py --train
```

Output:
```
Found 75 new messages to train (out of 225 total)
✓ Successfully trained 75/75 spam messages
Total spam trained: 225
Total ham trained: 300

✓ Bayes classifier has sufficient training data
```

### 3. Ongoing Maintenance

Set up a cron job to train daily:

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 2 AM)
0 2 * * * export IMAP_PASSWORD="your_password" && /home/change-me/rspamd-spam-train.py --train >> /var/log/rspamd-train.log 2>&1
```

Or use a systemd timer (more modern):

Create `/etc/systemd/system/rspamd-train.service`:
```ini
[Unit]
Description=Train Rspamd Bayes Classifier
After=network.target

[Service]
Type=oneshot
User=*** changeme ***
Environment="IMAP_PASSWORD=your_password"
ExecStart=/home/change-md/rspamd-spam-train.py --train
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/rspamd-train.timer`:
```ini
[Unit]
Description=Train Rspamd Bayes daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable it:
```bash
sudo systemctl enable rspamd-train.timer
sudo systemctl start rspamd-train.timer
```

## Understanding Bayes Training

### Minimum Requirements

Rspamd requires:
- **At least 200 spam messages**
- **At least 200 ham messages**

Until you reach these minimums, the `BAYES_SPAM` and `BAYES_HAM` scores won't appear in message headers.

### What Gets Trained

- **Spam folder (Junk)**: Messages you've manually classified as spam
- **Ham folder (INBOX)**: Messages you've kept as legitimate

### Best Practices

1. **Quality over quantity**: Only train on messages you're 100% sure about
2. **Balanced training**: Try to keep spam and ham counts roughly similar
3. **Regular updates**: Run training weekly as you classify more messages
4. **Review before training**: Make sure your folders are clean

### Verifying Bayes is Working

After training 200+ of each:

```bash
# Check a spam email - should see BAYES_SPAM score
./rspamd-ctl.sh --logs | grep BAYES

# Or check headers of incoming spam
# Look for: BAYES_SPAM(x.xx) in X-Spamd-Result header
```

## Troubleshooting

### "No spam-db specified" Error

This is normal. It means you haven't trained yet. The database is created automatically when you first train.

### IMAP Connection Failed

Check:
```bash
# Test IMAP connection
openssl s_client -connect localhost:993 -starttls imap

# Verify credentials
# Make sure imap_user and password are correct
```

### Messages Not Training

Check rspamd logs:
```bash
./rspamd-ctl.sh --logs | grep -i learn
```

### State File Issues

```bash
# Check state file
cat /tmp/rspamd-train-state.json

# Reset if corrupted
./rspamd-spam-train.py --reset
```

### Permission Denied

```bash
# Make sure script is executable
chmod +x ~/rspamd-spam-train.py

# Check state file permissions
ls -la /tmp/rspamd-train-state.json
```

## Advanced Usage

### Train from Different Folders

```bash
# Train from custom folders
./rspamd-spam-train.py --train \
  --spam-folder "INBOX/Spam" \
  --ham-folder "INBOX/NotSpam"
```

### Limit Messages Per Run

```bash
# Only train 100 messages at a time
./rspamd-spam-train.py --train --max 100
```

### Multiple Accounts

Create separate config files:
```bash
cp ~/rspamd-spam-train.py ~/rspamd-train-account1.py
cp ~/rspamd-spam-train.py ~/rspamd-train-account2.py

# Edit each with different imap_user and state_file
nano ~/rspamd-train-account1.py
nano ~/rspamd-train-account2.py
```

## Comparison with Stalwart's Built-in Training

| Feature | Rspamd | Stalwart Built-in |
|---------|--------|-------------------|
| Training Method | HTTP API | Parse message bodies |
| Complexity | Simple POST request | Extract and parse content |
| State Tracking | This script | This script |
| Per-user Bayes | No (global) | Yes (per account) |
| Minimum messages | 200 each | Configurable |

## Integration with Your Existing Workflow

Since you already have:
- ✅ Thunderbird connected to Stalwart
- ✅ Vetted Junk and Inbox folders
- ✅ Experience with training scripts

This new script:
- Uses the same IMAP connection you're familiar with
- Works with your existing folder structure
- Much simpler than parsing message bodies
- Can run on the same schedule as your old Stalwart training

## See Also

- [Rspamd Bayes Documentation](https://rspamd.com/doc/configuration/statistic.html)
- [Rspamd Learning API](https://rspamd.com/doc/modules/neural.html)
- Your original: [stalwart-spam-train.md](https://github.com/JimDunphy/Stalwart-Tools/blob/main/bin/stalwart-spam-train.md)

## License

MIT License (same as your original stalwart-spam-train.py)
