# Stalwart Spam Filter Training Tool

A Python utility to train Stalwart Mail Server's Bayes spam filter with email messages from files or directories.

## Features

- ✅ Train messages as spam or ham (legitimate email)
- ✅ Global training or per-account training
- ✅ Single file or batch directory processing
- ✅ Recursive directory scanning
- ✅ Progress indicators for batch operations
- ✅ Multiple authentication methods
- ✅ Comprehensive error handling and reporting
- ✅ Dry-run mode for testing

## Installation

### Requirements

- Python 3.7 or higher
- `requests` library (required)
- `tqdm` library (optional, for progress bars)

### Install Dependencies

```bash
# Install required dependencies
pip install requests

# Optional: Install tqdm for progress bars
pip install tqdm
```

Or install both at once:

```bash
pip install requests tqdm
```

### Install Script

```bash
# Copy to your local bin directory
cp stalwart-spam-train.py ~/bin/stalwart-spam-train
chmod +x ~/bin/stalwart-spam-train

# Or create a symlink
ln -s /path/to/stalwart-scripts/stalwart-spam-train.py ~/bin/stalwart-spam-train
```

## Authentication

The tool supports multiple authentication methods with the following precedence:

### 1. API Token (Recommended)

**Command line:**
```bash
stalwart-spam-train --token YOUR_API_TOKEN --type spam message.eml
```

**Environment variable:**
```bash
export STALWART_TOKEN=your_api_token_here
stalwart-spam-train --type spam message.eml
```

**Token file:**
```bash
echo "your_api_token_here" > ~/.stalwart-token
chmod 600 ~/.stalwart-token
stalwart-spam-train --type spam message.eml
```

### 2. Username/Password (Fallback)

```bash
stalwart-spam-train \
    --username admin \
    --password your_password \
    --type spam message.eml
```

### Creating an API Token

Use Stalwart's management API to create a token with `spam-filter-train` permission:

```bash
# Using Stalwart CLI or web interface
# Token must have Permission::SpamFilterTrain
```

## Usage

### Basic Usage

```bash
# Train single message as spam
stalwart-spam-train --type spam spam_message.eml

# Train single message as ham (legitimate)
stalwart-spam-train --type ham legitimate_message.eml
```

### Directory Training

```bash
# Train all emails in a directory as spam
stalwart-spam-train --type spam /path/to/spam/folder/

# Recursive directory scan
stalwart-spam-train --type spam --recursive /var/mail/spam/

# Custom file pattern
stalwart-spam-train --type spam --pattern "*.msg" /path/to/messages/
```

### Per-Account Training

Train spam filter for a specific user account:

```bash
# Train for specific user
stalwart-spam-train --type spam --account user@example.com spam/

# Train ham for specific user
stalwart-spam-train --type ham --account john.doe ham/
```

### Custom Server

```bash
# Specify server URL
stalwart-spam-train \
    --server https://mail.example.org \
    --token YOUR_TOKEN \
    --type spam \
    spam_folder/

# Or use environment variable
export STALWART_SERVER=https://mail.example.org
stalwart-spam-train --type spam spam_folder/
```

### Advanced Options

```bash
# Dry run (show what would be done)
stalwart-spam-train --dry-run --type spam --recursive spam/

# Verbose output
stalwart-spam-train --verbose --type spam spam/

# Stop on first error
stalwart-spam-train --fail-fast --type spam spam/

# Combine options
stalwart-spam-train \
    --type spam \
    --account user@example.com \
    --recursive \
    --verbose \
    --pattern "*.eml" \
    /var/mail/reported-spam/
```

## Understanding Authentication vs Account

**Important distinction:**

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `--username` / `--password` | **WHO YOU AUTHENTICATE AS**<br>Your login credentials to access the API | `--username admin`<br>`--username user@example.com` |
| `--account` | **WHO YOU'RE TRAINING FOR**<br>Which user's spam filter to train<br>(Optional: omit for global training) | `--account user@example.com` |

### Examples

**Admin training for a user:**
```bash
# Admin "admin" trains user@example.com's filter
--username admin --password xxx --account user@example.com
```

**User training their own filter:**
```bash
# User trains their own filter
--username user@example.com --password xxx --account user@example.com
```

**Global training (no --account):**
```bash
# Trains global filter affecting all users
--username admin --password xxx
```

## Command-Line Options

```
usage: stalwart-spam-train.py [-h] --type {spam,ham} [--account ACCOUNT]
                              [--server SERVER] [--token TOKEN]
                              [--username USERNAME] [--password PASSWORD]
                              [--recursive] [--pattern PATTERN] [--fail-fast]
                              [--dry-run] [--verbose]
                              path

positional arguments:
  path                  Path to email file or directory

required arguments:
  --type {spam,ham}     Training type: spam (unwanted) or ham (legitimate)

authentication arguments:
  --token TOKEN         API token for authentication (recommended)
  --username USERNAME   Username for basic auth (WHO YOU LOG IN AS)
  --password PASSWORD   Password for basic auth

training target:
  --account ACCOUNT     Email account to train FOR (omit for global training)

server options:
  --server SERVER       Stalwart server URL (default: $STALWART_SERVER or
                        http://localhost:8080)

file scanning:
  --recursive           Recursively scan directories
  --pattern PATTERN     File pattern to match (e.g., "*.eml")

control options:
  --fail-fast           Stop on first error (default: continue and report)
  --dry-run             Show what would be done without training
  --verbose, -v         Verbose output
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `STALWART_SERVER` | Server URL | `http://localhost:8080` |
| `STALWART_TOKEN` | API authentication token | None |

## Supported File Formats

The tool automatically scans for common email file extensions:

- `.eml` - Standard RFC822 email files
- `.msg` - Outlook message files (if in MIME format)
- `.txt` - Plain text email files
- `.mbox` - Mbox format files (multiple messages per file)

**Note:** All files must be in valid MIME format with email headers. The tool validates that messages contain at least one valid header (e.g., `From:`, `Subject:`, etc.) before training.

### Mbox Files

Mbox files contain multiple email messages in a single file and are used by:
- **Thunderbird** - Local folders and Junk folders
- **Dovecot** - Mail storage backend
- **Evolution** - Email client storage
- **Apple Mail** - Mailbox exports

The tool automatically detects `.mbox` files and processes each message individually with progress tracking. This is ideal for:
- Training from Thunderbird's Junk folder (years of pre-classified spam)
- Bulk importing spam corpora
- Processing mail archives
- Training from IMAP folder exports

**Performance:** Mbox files are processed sequentially. A 10,000 message mbox will take approximately 10-20 minutes depending on network latency.

## Examples

### Example 1: Train User's Spam Folder

User has reported spam messages in a folder:

```bash
# Train all messages as spam for user@example.com
stalwart-spam-train \
    --type spam \
    --account user@example.com \
    --recursive \
    ~/mail/user@example.com/reported-spam/
```

### Example 2: Bulk Import Spam Corpus

Training with a large spam corpus:

```bash
# Set up environment
export STALWART_SERVER=https://mail.example.org
export STALWART_TOKEN=your_api_token

# Train large spam dataset
stalwart-spam-train \
    --type spam \
    --recursive \
    --verbose \
    /datasets/spam-corpus/
```

### Example 3: Train Ham and Spam for New User

Setting up baseline training for a new user:

```bash
# Train ham (legitimate emails)
stalwart-spam-train \
    --type ham \
    --account newuser@example.com \
    ~/training-data/ham/

# Train spam
stalwart-spam-train \
    --type spam \
    --account newuser@example.com \
    ~/training-data/spam/
```

### Example 4: Train from Thunderbird Junk Folder

Train using your existing Junk folder (requires knowing your Thunderbird profile path):

```bash
# Find your Thunderbird profile
find ~/.thunderbird -name Junk -type f

# Train from Junk folder (typically has thousands of spam messages)
stalwart-spam-train \
    --type spam \
    --account user@example.com \
    ~/.thunderbird/abc123.default/Mail/Local\ Folders/Junk

# Example output:
# Processing mbox: Junk
#   Training from Junk: 100%|██████| 5234/5234 [8:42<00:00, 10.02msg/s]
#
# Training Summary
# Type:       SPAM
# Files:      0 individual, 1 mbox
# Total:      5234 messages
# Successful: 5234
# Failed:     0
```

### Example 5: Export and Train from Gmail

Export spam from Gmail and train:

```bash
# 1. Export via Google Takeout (gets .mbox file)
# 2. Download Spam.mbox

# Train from exported Gmail spam
stalwart-spam-train \
    --type spam \
    --account user@example.com \
    ~/Downloads/Takeout/Mail/Spam.mbox
```

### Example 6: Scheduled Training Script

Create a cron job to process user-reported spam:

```bash
#!/bin/bash
# train-reported-spam.sh

STALWART_TOKEN=$(cat ~/.stalwart-token)
SPAM_DIR=/var/mail/reported-spam
PROCESSED_DIR=/var/mail/processed-spam

# Train all new spam reports
/usr/local/bin/stalwart-spam-train \
    --type spam \
    --recursive \
    --token "$STALWART_TOKEN" \
    "$SPAM_DIR"

# Move processed messages
if [ $? -eq 0 ]; then
    mv "$SPAM_DIR"/*.eml "$PROCESSED_DIR"/ 2>/dev/null
fi
```

## How It Works

### Training Process

1. **File Discovery**: Scans the specified path for email files
2. **Validation**: Verifies each file contains valid email headers
3. **API Request**: Sends POST request to Stalwart API endpoint:
   - Global: `/api/spam-filter/train/{spam|ham}`
   - Per-user: `/api/spam-filter/train/{spam|ham}/{account_id}`
4. **Bayes Update**: Stalwart updates its Bayes classifier:
   - Tokenizes the message
   - Updates spam/ham token weights
   - Increments spam/ham learn counters

### Authentication Flow

```
1. Check --token argument
   ↓ not provided
2. Check $STALWART_TOKEN env var
   ↓ not set
3. Check ~/.stalwart-token file
   ↓ not found
4. Check --username/--password arguments
   ↓ not provided
5. Exit with error
```

### API Communication

The tool sends messages to Stalwart using:

```http
POST /api/spam-filter/train/spam HTTP/1.1
Host: mail.example.org
Authorization: Bearer YOUR_TOKEN
Content-Type: message/rfc822
Accept: application/json

[Raw email message content in MIME format]
```

Response on success:
```json
{
  "data": null
}
```

## Troubleshooting

### Common Issues

#### 1. Authentication Failed

```
Error: HTTP 401 Unauthorized
```

**Solution:**
- Verify your API token is correct
- Check token has `spam-filter-train` permission
- Ensure username/password are correct

#### 2. Invalid Email Format

```
Error: Invalid email format (missing headers)
```

**Solution:**
- Ensure files are in proper MIME format
- Check files contain email headers (`From:`, `Subject:`, etc.)
- Try opening the file in an email client to verify

#### 3. Connection Refused

```
Network error: Connection refused
```

**Solution:**
- Verify server URL is correct
- Check Stalwart is running
- Verify firewall/network access
- Test with: `curl http://localhost:8080/api/health`

#### 4. No Files Found

```
Error: No email files found in /path/to/folder
```

**Solution:**
- Check path exists and is correct
- Use `--recursive` for subdirectories
- Use `--pattern` to specify custom file extensions
- Verify files have recognized extensions (`.eml`, `.msg`, etc.)

#### 5. Mbox File Issues

**Error: "Error reading mbox file"**

**Solution:**
- Ensure file is valid mbox format (not Maildir)
- Check file permissions (readable)
- Verify file isn't corrupted
- Thunderbird: Use the file directly, not the `.msf` index file

**Finding Thunderbird mbox files:**
```bash
# Linux/Unix
~/.thunderbird/*/Mail/Local\ Folders/Junk
~/.thunderbird/*/ImapMail/*/Junk

# macOS
~/Library/Thunderbird/Profiles/*/Mail/Local\ Folders/Junk

# Windows
%APPDATA%\Thunderbird\Profiles\*\Mail\Local Folders\Junk
```

**Note:** Thunderbird stores each folder as an mbox file without extension. The `.msf` files are index files and should NOT be used.

### Debug Mode

For detailed debugging:

```bash
# Verbose output shows each file processed
stalwart-spam-train --verbose --type spam folder/

# Dry run shows what would be processed
stalwart-spam-train --dry-run --recursive --type spam folder/
```

## Performance Notes

- **Batch Size**: No built-in limit, processes all files in sequence
- **Network**: Each message is a separate HTTP request (~50-100 ms per message)
- **Large Batches**: For 10,000+ messages, consider:
  - Running in background
  - Splitting into smaller batches
  - Using `--verbose` to monitor progress

**Estimated Times:**
- 100 messages: ~10 seconds
- 1,000 messages: ~1-2 minutes
- 10,000 messages: ~10-20 minutes

**Mbox Performance:**
- Processing overhead is minimal (Python's built-in `mailbox` module is efficient)
- Progress bars show messages/second throughput
- Network latency is the primary bottleneck, not file parsing
- A large Thunderbird Junk folder (5,000-10,000 messages) typically takes 8-15 minutes
- Consider training during off-peak hours for very large mbox files

## Security Considerations

### Token Storage

```bash
# Secure token file
chmod 600 ~/.stalwart-token

# Or use environment variable in secure context
export STALWART_TOKEN=$(secret-tool lookup service stalwart)
```

### HTTPS

Always use HTTPS for production:

```bash
# Bad (credentials sent in plaintext)
--server http://mail.example.org

# Good (encrypted connection)
--server https://mail.example.org
```

### Permissions

The API requires `Permission::SpamFilterTrain` which should be restricted to:
- Mail administrators
- Automated training systems
- Trusted users with spam reporting access

## Integration Examples

### With Mail Client Filters

Thunderbird filter to save spam:

```
If [SpamAssassin] contains [spam]
Then: Copy to folder: ~/reported-spam/
```

Then train periodically:
```bash
stalwart-spam-train --type spam ~/reported-spam/
```

### With IMAP Move Scripts

```python
# imap-spam-trainer.py
# Watches IMAP folder and trains Stalwart
import imaplib
import subprocess

# Connect to IMAP, select "Spam" folder
# For each message, save and train
subprocess.run([
    'stalwart-spam-train',
    '--type', 'spam',
    '--account', user_email,
    saved_message_path
])
```

## Contributing

Improvements and bug reports welcome! Consider adding:
- Parallel training with thread pool for faster processing
- CSV export of training statistics
- Integration with dovecot/cyrus IMAP
- Maildir format support
- Automatic detection and training from IMAP folders

## License

MIT License

## See Also

- [Stalwart API Documentation](https://stalw.art/docs/api/management/endpoints/)
- [Bayes Spam Filtering](https://en.wikipedia.org/wiki/Naive_Bayes_spam_filtering)
- [RFC 5322 - Internet Message Format](https://www.rfc-editor.org/rfc/rfc5322)
