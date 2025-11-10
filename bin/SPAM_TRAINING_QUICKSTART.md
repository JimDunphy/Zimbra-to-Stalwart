# Spam Training Tool - Quick Start

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or install manually
pip install requests tqdm

# Make script executable (if needed)
chmod +x stalwart-spam-train.py
```

See `INSTALL.md` for detailed installation instructions and troubleshooting.

## Understanding --username vs --account

**Key distinction:**
- `--username` / `--password` = **WHO YOU LOG IN AS** (your credentials)
- `--account` = **WHO YOU'RE TRAINING FOR** (which user's spam filter)

**Examples:**
```bash
# Admin trains user's filter
--username admin --password xxx --account user@example.com

# User trains their own filter
--username user@example.com --password xxx --account user@example.com

# Global training (no --account)
--username admin --password xxx
```

## Quick Examples

### Single File

```bash
# Train one message as spam
./stalwart-spam-train.py --type spam --token YOUR_TOKEN spam.eml

# Train one message as ham (legitimate)
./stalwart-spam-train.py --type ham --token YOUR_TOKEN legit.eml
```

### Directory

```bash
# Train all emails in folder as spam
./stalwart-spam-train.py --type spam --token YOUR_TOKEN spam_folder/

# Recursive scan
./stalwart-spam-train.py --type spam --token YOUR_TOKEN --recursive /var/mail/spam/
```

### Mbox Files (Thunderbird, Dovecot, etc.)

```bash
# Train from Thunderbird Junk folder
./stalwart-spam-train.py --type spam --token YOUR_TOKEN ~/.thunderbird/profile/Mail/Local\ Folders/Junk

# Train from exported mbox
./stalwart-spam-train.py --type spam --token YOUR_TOKEN spam.mbox

# Per-user training from mbox
./stalwart-spam-train.py \
    --type spam \
    --username admin \
    --password xxx \
    --account user@example.com \
    Junk.mbox
```

### Per-User Training

```bash
# Train for specific user (admin authenticating)
./stalwart-spam-train.py \
    --type spam \
    --username admin \
    --password xxx \
    --account user@example.com \
    spam_folder/

# User training their own filter
./stalwart-spam-train.py \
    --type spam \
    --username user@example.com \
    --password xxx \
    --account user@example.com \
    spam_folder/
```

## Authentication Setup

### Option 0: Interactive Prompt (Easiest)

Just run the command - it will prompt for username/password:
```bash
./stalwart-spam-train.py --type spam spam_folder/
# Will prompt: Username:
# Will prompt: Password: (hidden)
```

### Option 1: Environment Variable (Recommended)

```bash
export STALWART_TOKEN=your_api_token_here
./stalwart-spam-train.py --type spam spam_folder/
```

### Option 2: Token File

```bash
echo "your_api_token_here" > ~/.stalwart-token
chmod 600 ~/.stalwart-token
./stalwart-spam-train.py --type spam spam_folder/
```

### Option 3: Command Line

```bash
./stalwart-spam-train.py --token YOUR_TOKEN --type spam spam_folder/
```

## Reset Corrupted Bayes Model

If your Bayes classifier is broken (e.g., everything scores as spam), purge and retrain:

```bash
# Purge and retrain account-specific model
./stalwart-spam-train.py --type spam --purge-first \
    --account user@example.com \
    --username user@example.com --password xxx \
    --server https://mail.example.com/ \
    spam/JunkMail.mbox

# Then train ham
./stalwart-spam-train.py --type ham \
    --account user@example.com \
    --username user@example.com --password xxx \
    --server https://mail.example.com/ \
    ham/Sent.mbox

# Purge global model (requires admin)
./stalwart-spam-train.py --type spam --purge-first \
    --username admin --password xxx \
    --server https://mail.example.com/ \
    spam/
```

**Warning:** `--purge-first` deletes ALL previous training data. Only use when resetting a corrupted model.

## Common Workflows

### Show Message Counts

```bash
# Show count of messages (no authentication needed)
./stalwart-spam-train.py --show-count spam_folder/

# Show count in mbox file
./stalwart-spam-train.py --show-count JunkMail.mbox

# Show count recursively with details
./stalwart-spam-train.py --show-count --recursive --verbose ~/thunderbird/
```

### Limit Training (--count N)

```bash
# Train only first 200 messages (useful for testing or limiting load)
./stalwart-spam-train.py --type spam --token YOUR_TOKEN --count 200 spam.mbox

# Test with small batch first
./stalwart-spam-train.py --type spam --token YOUR_TOKEN --count 10 --verbose spam/

# Train 500 spam messages from large mbox
./stalwart-spam-train.py --type spam --account user@example.com \
    --username admin --password xxx --count 500 JunkMail.mbox
```

### Test Run (Dry-run)

```bash
# See what would be trained without actually doing it
./stalwart-spam-train.py --dry-run --type spam --recursive spam/
```

### Verbose Mode

```bash
# See detailed progress for each file
./stalwart-spam-train.py --verbose --type spam spam/
```

### Custom Server

```bash
# Connect to remote server
export STALWART_SERVER=https://mail.example.org
export STALWART_TOKEN=your_token
./stalwart-spam-train.py --type spam spam/
```

## Troubleshooting

### No files found

```bash
# Check what files exist
ls -la spam_folder/

# Try recursive mode
./stalwart-spam-train.py --type spam --recursive spam_folder/

# Specify pattern
./stalwart-spam-train.py --type spam --pattern "*.msg" spam_folder/
```

### Authentication errors

```bash
# Verify token is set
echo $STALWART_TOKEN

# Test server connection
curl -H "Authorization: Bearer $STALWART_TOKEN" \
     http://localhost:8080/api/health
```

### Invalid email format

Email files must have headers like:
```
From: sender@example.com
To: recipient@example.com
Subject: Email subject
Date: Mon, 01 Jan 2024 10:00:00 +0000

Email body here...
```

### Finding Thunderbird mbox files

```bash
# Linux/Unix
~/.thunderbird/*/Mail/Local\ Folders/Junk
~/.thunderbird/*/ImapMail/*/Junk

# macOS
~/Library/Thunderbird/Profiles/*/Mail/Local\ Folders/Junk

# Windows
%APPDATA%\Thunderbird\Profiles\*\Mail\Local Folders\Junk
```

## Testing Spam Classification

```bash
# Test how a message would be scored
./stalwart-spam-train.py \
    --test-message spam.eml \
    --username admin \
    --password xxx \
    --server https://mail.example.com

# Test for specific account (uses account's Bayes model)
./stalwart-spam-train.py \
    --test-message spam.eml \
    --username admin \
    --password xxx \
    --server https://mail.example.com \
    --account user@example.com

# Output shows:
# - Total spam score
# - All triggered rules and their scores
# - Bayes score (if trained)
# - Interpretation (ham/spam/borderline)
```

**Note:** There is currently no API endpoint to view training statistics (e.g., how many spam/ham messages trained). Use `--test-message` to verify Bayes is working - if you see a BAYES tag in the output, it's active.

## Full Documentation

See `stalwart-spam-train.md` for complete documentation including:
- All command-line options
- API details
- Integration examples
- Performance notes
- Security considerations

See `SPAM_FILTER_GUIDE.md` for understanding:
- How spam scoring works
- Why Bayes needs both spam AND ham training
- What `$PHISHING` and other symbols mean
- Testing and debugging spam filters
- Configuration tuning
