# Stalwart Spam Filter - Complete Guide

## Table of Contents
1. [Understanding Spam Scores](#understanding-spam-scores)
2. [Bayes Classification](#bayes-classification)
3. [Rules and Symbols](#rules-and-symbols)
4. [Testing and Debugging](#testing-and-debugging)
5. [Configuration](#configuration)

---

## Understanding Spam Scores

### How Scoring Works

Stalwart uses an **additive scoring system**:

```
Total Score = Bayes Score + Rule1 Score + Rule2 Score + ...
```

**Example:**
```
BAYES                           5.10
HACKED_WP_PHISHING              4.50
MISSING_DATE                    0.50
SPF_NA                          0.30
───────────────────────────────────
Total:                         10.40  → SPAM
```

**Threshold (typical):**
- Score < 5.0: HAM (legitimate)
- Score 5.0-10.0: Borderline
- Score > 10.0: SPAM

### Why Everything Scores 5.10 (Your Problem)

**The Issue:** Bayes classifier requires **BOTH** spam and ham training to work.

Looking at Stalwart's code (`bayes.rs:190-196`):

```rust
let (spam_learns, ham_learns) = self.bayes_weights_for_token(...);

if spam_learns < classifier.min_learns || ham_learns < classifier.min_learns {
    return Ok(None); // Bayes doesn't run!
}
```

**Your situation:**
- Spam trained: 280 messages ✓
- Ham trained: 0 messages ✗
- `spam-filter.bayes.min-learns`: 200 (default)

**Result:** Bayes is disabled! The 5.10 score is likely a default/fallback value.

**Solution:** Train ham messages!

```bash
# Train legitimate email (Sent folder, Inbox, etc.)
./stalwart-spam-train.py \
    --type ham \
    --account user@example.com \
    --username user@example.com \
    --password xxx \
    --server https://mail.example.com/ \
    ~/path/to/ham/

# Aim for similar counts: 200-500 ham for your 280 spam
```

---

## Bayes Classification

### Configuration Settings

```toml
[spam-filter.bayes]
# Minimum messages required before Bayes activates
min-learns = 200              # Need 200+ spam AND 200+ ham

# Token probability thresholds
score.spam = 0.7              # If P(token|spam) > 0.7 → likely spam
score.ham = 0.5               # If P(token|ham) < 0.5 → likely ham

# Enable per-account Bayes (separate filters per user)
[spam-filter.bayes.account]
enable = true
score.spam = 0.7
score.ham = 0.5
```

### What These Mean

**`min-learns = 200`:**
- Bayes needs statistical significance
- With <200 messages, patterns aren't reliable
- Must have 200+ spam **AND** 200+ ham trained

**`score.spam = 0.7` and `score.ham = 0.5`:**
- These are **token probability thresholds**, not spam scores
- Bayes calculates: "What's P(this word appears in spam vs ham)?"
- If P(token|spam) / P(token|all) > 0.7 → token is "spammy"
- If P(token|ham) / P(token|all) > 0.5 → token is "hammy"
- Final Bayes score is 0-10 range based on all tokens

### How Bayes Training Works

When you train a message:

1. **Tokenization:**
   - Extracts words, phrases, N-grams from subject & body
   - Extracts metadata: From domain, IP, ASN, etc.

2. **Weight Updates:**
   - For each token, increments `spam_count` or `ham_count`
   - Stores in key-value store: `KV_BAYES_MODEL_USER` or `KV_BAYES_MODEL_GLOBAL`

3. **Classification:**
   - For new email, extracts same tokens
   - Looks up `spam_count` and `ham_count` for each token
   - Calculates probability: `P(spam|tokens)` using Naive Bayes
   - Returns score 0-10

**Key Token:** `TokenHash::default()` stores the learn counts:
- `spam_learns` = total spam messages trained
- `ham_learns` = total ham messages trained

---

## Rules and Symbols

### Where is `$PHISHING` Defined?

**Short answer:** It's a **built-in symbol** from Stalwart's spam filter engine.

### Three Types of Symbols

#### 1. Built-in Checks (Engine Code)
These are hardcoded in Stalwart's source:

```rust
// Examples from Stalwart source
$PHISHING           // Checks for phishing patterns
$SPF_FAIL           // SPF verification failed
$DKIM_FAIL          // DKIM signature failed
$DMARC_FAIL         // DMARC policy failed
$FROM_NO_DN         // From header has no display name
$MISSING_DATE       // Email missing Date header
$MISSING_MIME_VERSION
$FORGED_SENDER
$AUTH_NA            // No authentication
```

#### 2. External List Lookups (DNSBL, SURBL, etc.)
Queries external reputation databases:

```
$CRACKED_SURBL      // Domain found in SURBL cracked sites list
$PH_SURBL_MULTI     // Phishing URL in SURBL
$DBL_PHISH          // Domain in Spamhaus DBL phishing list
$DBL_ABUSE_PHISH    // Domain in DBL abuse list
$URIBL_BLACK        // URL in URIBL blacklist
$PHISHED_OPENPHISH  // URL in OpenPhish feed
$PHISHED_PHISHTANK  // URL in PhishTank feed
```

#### 3. Custom Rules (Your Definitions)
Defined in your config:

```toml
[spam-filter.rule.stwt_hacked_wp_phishing]
rule = "($X_HDR_X_PHP_ORIGINATING_SCRIPT || $HAS_PHPMAILER_SIG) && $HAS_WP_URI && ($PHISHING || $CRACKED_SURBL || $PH_SURBL_MULTI || $DBL_PHISH || $DBL_ABUSE_PHISH || $URIBL_BLACK || $PHISHED_OPENPHISH || $PHISHED_PHISHTANK)"
score = 4.5
tag = "HACKED_WP_PHISHING"
```

**This means:**
- If email has PHP mailer headers (`$X_HDR_X_PHP_ORIGINATING_SCRIPT`)
- AND contains WordPress URLs (`$HAS_WP_URI`)
- AND triggers ANY phishing detector
- → Add 4.5 to spam score and tag as `HACKED_WP_PHISHING`

### Finding Symbol Definitions

**Built-in symbols:** Search Stalwart source code
```bash
cd ~/stalwart/stalwart
grep -r "PHISHING" crates/spam-filter/
grep -r "SPF_FAIL" crates/spam-filter/
```

**External lists:** Check configuration
```bash
# In Stalwart config
[spam-filter.dnsbl]
# Lists DNSBL servers being queried

[spam-filter.lookup]
# Lists SURBL/URIBL servers
```

**Custom rules:** Check your config
```bash
# In Stalwart config
[spam-filter.rule.*]
# Your custom rule definitions
```

---

## Testing and Debugging

### Test Message Classification

Use the new `--test-message` feature to see exactly how a message scores:

```bash
./stalwart-spam-train.py \
    --test-message spam.eml \
    --username user@example.com \
    --password xxx \
    --server https://mail.example.com/ \
    --account user@example.com
```

**Output:**
```
======================================================================
SPAM SCORE: 10.45
======================================================================

TRIGGERED RULES:
----------------------------------------------------------------------
  BAYES                                        5.10  [add_header]
  HACKED_WP_PHISHING                           4.50  [add_header]
  MISSING_DATE                                 0.50  [add_header]
  SPF_NA                                       0.30  [add_header]
  FROM_NO_DN                                   0.05  [add_header]

INTERPRETATION:
  ✗ SPAM (likely unwanted)
```

### API Endpoint for Classification

You can also test directly via API:

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: message/rfc822" \
  --data-binary @spam.eml \
  "https://mail.example.com/api/spam-filter/classify?account_id=user@example.com"
```

**Response:**
```json
{
  "data": {
    "score": 10.45,
    "tags": {
      "BAYES": {"value": 5.10, "action": "add_header"},
      "HACKED_WP_PHISHING": {"value": 4.50, "action": "add_header"},
      "MISSING_DATE": {"value": 0.50, "action": "add_header"}
    }
  }
}
```

### Debugging Checklist

**1. Check Bayes training status:**
```bash
# Currently no direct API for this - working on adding it
# For now, check logs or use test messages to see if Bayes scores
```

**2. Test with known spam:**
```bash
./stalwart-spam-train.py \
    --test-message known-spam.eml \
    --username admin --password xxx \
    --server https://mail.example.com/
```

**3. Test with known ham:**
```bash
./stalwart-spam-train.py \
    --test-message known-ham.eml \
    --username admin --password xxx \
    --server https://mail.example.com/
```

**4. Check rule definitions:**
```bash
# In Stalwart admin UI or config file
# Look for [spam-filter.rule.*] sections
```

---

## Configuration

### Key Configuration Sections

#### Bayes Settings

```toml
[spam-filter.bayes]
min-learns = 200              # Minimum messages before Bayes activates
score.spam = 0.7              # Spam token threshold
score.ham = 0.5               # Ham token threshold
min-token-hits = 2            # Token must appear 2+ times
min-tokens = 11               # Need 11+ tokens to classify
min-prob-strength = 0.05      # Minimum probability strength
```

#### Global vs Per-Account

```toml
# Global Bayes (one model for all users)
[spam-filter.bayes]
enable = true

# Per-account Bayes (separate model per user)
[spam-filter.bayes.account]
enable = true                 # Recommended for multi-user setups
```

**When to use per-account:**
- Different users get different spam (e.g., tech vs marketing)
- Users want to train their own filters
- Privacy: user training data stays separate

**When to use global:**
- Single user or small team
- Everyone gets similar email
- Want faster training (larger dataset)

#### Custom Rules

```toml
[spam-filter.rule.my_custom_rule]
rule = "$SPF_FAIL && $DKIM_FAIL"
score = 5.0
tag = "AUTH_FAILURE"
description = "Both SPF and DKIM failed"
```

#### Thresholds and Actions

```toml
[spam-filter.threshold]
# Score ranges and actions
spam = "reject"                    # Score >= 15: Reject
discard = 15.0
add-header = 5.0                   # Score >= 5: Add X-Spam headers
rewrite-subject = 10.0             # Score >= 10: Add [SPAM] to subject
```

### Recommended Initial Setup

```toml
[spam-filter.bayes]
min-learns = 100              # Lower for initial testing
enable = true

[spam-filter.bayes.account]
enable = true                 # Per-user filters
min-learns = 100              # Lower for initial testing

[spam-filter.threshold]
discard = 20.0                # Be conservative at first
reject = 25.0
```

---

## Training Strategy

### 1. Initial Training

**Minimum viable training:**
- 100-200 spam messages
- 100-200 ham messages

**Step 1: Count available messages**
```bash
# Check how many spam messages you have
./stalwart-spam-train.py --count ~/thunderbird/*/Mail/Local\ Folders/Junk

# Check how many ham messages you have
./stalwart-spam-train.py --count ~/thunderbird/*/Mail/Local\ Folders/Sent

# Example output:
# ======================================================================
# MESSAGE COUNT
# ======================================================================
# Path: /home/user/.thunderbird/abc.default/Mail/Local Folders/Junk
#
# Mbox files: 1
#   Junk                                          3,245 messages  (45,678,901 bytes)
#
# Total messages in mbox files: 3,245
#
# ======================================================================
# GRAND TOTAL: 3,245 messages
# ======================================================================
```

**Sources for ham:**
- Sent folder (guaranteed legitimate)
- Inbox (emails you've kept)
- Important/Archive folders

**Sources for spam:**
- Junk/Spam folder
- Reported spam from users
- Public spam corpora

**Step 2: Train balanced amounts**
```bash
# If you have 3,245 spam, train 3,000-3,500 ham for balance
./stalwart-spam-train.py --type spam --account user@example.com spam/
./stalwart-spam-train.py --type ham --account user@example.com ham/
```

### 2. Ongoing Training

**Auto-training:** Configure IMAP folders:
```toml
[spam-filter.auto-learn]
enable = true
spam-folder = "Junk"          # Moving to Junk trains as spam
ham-folder = "Inbox"          # Keeping in Inbox trains as ham
```

**Manual training:** Users can train by moving messages:
- Move to Junk folder → trains as spam
- Move from Junk to Inbox → trains as ham (correction)

### 3. Balanced Training

Stalwart checks for balance to prevent bias:

```rust
// From bayes.rs:321-330
let result = if spam_learns > 0.0 || ham_learns > 0.0 {
    if learn_spam {
        (spam_learns / (ham_learns + 1.0)) <= 1.0 / min_balance
    } else {
        (ham_learns / (spam_learns + 1.0)) <= 1.0 / min_balance
    }
} else {
    false
};
```

**What this means:**
- If ratio of spam:ham > 2:1, stop training more spam
- If ratio of ham:spam > 2:1, stop training more ham
- Prevents overwhelming the model with one class

**Your current situation:**
- Spam: 280, Ham: 0
- Ratio: ∞:1 (extremely imbalanced!)
- **Action needed:** Train ~300 ham messages ASAP

---

## Next Steps

1. **Train ham immediately:**
   ```bash
   ./stalwart-spam-train.py --type ham --account user@example.com \
     ~/thunderbird/profile/Mail/Local\ Folders/Sent
   ```

2. **Test classification:**
   ```bash
   ./stalwart-spam-train.py --test-message spam.eml \
     --account user@example.com --username user@example.com --password xxx
   ```

3. **Monitor scores:**
   - Check X-Spam-Score headers on incoming mail
   - Use `--test-message` on borderline messages
   - Adjust thresholds as needed

4. **Fine-tune:**
   - Add custom rules for your specific spam patterns
   - Adjust score weights
   - Train more messages in underrepresented categories

---

## Reference: Common Built-in Symbols

| Symbol | Meaning |
|--------|---------|
| `$BAYES` | Bayesian probability score |
| `$SPF_PASS` / `$SPF_FAIL` / `$SPF_NA` | SPF authentication |
| `$DKIM_PASS` / `$DKIM_FAIL` / `$DKIM_NA` | DKIM signature |
| `$DMARC_PASS` / `$DMARC_FAIL` / `$DMARC_NA` | DMARC policy |
| `$ARC_PASS` / `$ARC_FAIL` / `$ARC_NA` | ARC authentication |
| `$FROM_NO_DN` | From header missing display name |
| `$FORGED_SENDER` | From address doesn't match envelope |
| `$MISSING_DATE` | Email missing Date header |
| `$MISSING_MIME_VERSION` | Missing MIME-Version header |
| `$MISSING_TO` | Missing To header |
| `$MISSING_SUBJECT` | Missing Subject header |
| `$PHISHING` | Phishing patterns detected |
| `$MALWARE` | Malware detected |
| `$HAS_WP_URI` | Contains WordPress URL |
| `$HAS_PHPMAILER_SIG` | PHPMailer signature found |
| `$X_HDR_*` | Custom X-Headers present |

Check Stalwart docs and source for complete list: `crates/spam-filter/src/modules/`
