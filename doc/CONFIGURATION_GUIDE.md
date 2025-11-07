# Stalwart Configuration Guide

## Overview

This guide explains how Stalwart's configuration system works, with a focus on managing trusted networks and controlling spam filtering for relay hosts. As a C programmer new to Rust, you'll find this guide approaches the system from a practical, implementation-focused perspective.

## Table of Contents

1. [Configuration System Architecture](#configuration-system-architecture)
2. [How config.toml Works](#how-configtoml-works)
3. [Declaring and Using Configuration Keywords](#declaring-and-using-configuration-keywords)
4. [Trusted Networks and Relay Hosts](#trusted-networks-and-relay-hosts)
5. [Disabling Spam Filtering for Trusted Relays](#disabling-spam-filtering-for-trusted-relays)
6. [Practical Examples](#practical-examples)

---

## Configuration System Architecture

Stalwart uses a sophisticated configuration system built around three main components:

### 1. **Config Parser** (`crates/utils/src/config/`)
The low-level TOML parser that reads and validates configuration files.

### 2. **Expression Engine** (`crates/common/src/expr/`)
A powerful expression evaluator that supports:
- Conditional logic (if/then/else blocks)
- Variables (remote_ip, authenticated_as, etc.)
- Functions and operators
- Dynamic evaluation at runtime

### 3. **IfBlock System** (`crates/common/src/expr/if_block.rs`)
The core abstraction that allows configuration values to be:
- Static: `spam-filter.enable = true`
- Dynamic: Evaluated based on conditions like IP address, authentication status, port, etc.

---

## How config.toml Works

### Basic Structure

Configuration files use TOML format with a hierarchical structure:

```toml
[section.subsection]
key = "value"
```

### Static vs Dynamic Configuration

**Static Configuration:**
```toml
[session.data]
max-message-size = 104857600  # 100MB
```

**Dynamic Configuration (IfBlocks):**
```toml
# Example: Different behavior based on local port
[[session.data.add-headers.received.if]]
eq = "local_port"
then = "true"

[[session.data.add-headers.received.else]]
then = "false"
```

Or using the shorthand syntax:
```toml
session.data.add-headers.received = "local_port == 25"
```

---

## Declaring and Using Configuration Keywords

### How Keywords Are Declared

Configuration keywords are declared in Rust code within the `crates/common/src/config/` directory. Let's trace through an example:

#### Step 1: Define the Configuration Structure

Location: `crates/common/src/config/smtp/session.rs`

```rust
pub struct Data {
    pub spam_filter: IfBlock,      // Can be conditional
    pub max_message_size: IfBlock,
    pub add_received_spf: IfBlock,
    // ... other fields
}
```

#### Step 2: Parse Configuration Values

In the same file, the `parse()` method reads values from config.toml:

```rust
impl SessionConfig {
    pub fn parse(config: &mut Config) -> Self {
        let has_rcpt_vars = TokenMap::default().with_variables(SMTP_RCPT_TO_VARS);

        // Parse spam filter configuration
        if let Some(if_block) = IfBlock::try_parse(
            config,
            "session.data.spam-filter",  // The keyword in config.toml
            &has_rcpt_vars               // Variables available in expressions
        ) {
            session.data.spam_filter = if_block;
        }
        // ...
    }
}
```

#### Step 3: Use at Runtime

Location: `crates/smtp/src/inbound/data.rs`

```rust
// Evaluate the spam_filter IfBlock at runtime
let should_filter = self.server.eval_if(
    &self.server.core.smtp.session.data.spam_filter,
    self,
    self.data.session_id,
).await;
```

### Available Variables in Expressions

The expression engine provides access to session context:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `remote_ip` | Client's IP address | `192.168.1.100` |
| `local_port` | Server port receiving connection | `25`, `587`, `465` |
| `authenticated_as` | Username if authenticated | `user@domain.com` or empty |
| `listener` | Listener name | `"smtp"`, `"submission"` |
| `sender` | MAIL FROM address | `sender@example.com` |
| `sender_domain` | Domain from MAIL FROM | `example.com` |
| `rcpt` | RCPT TO address | `recipient@example.com` |
| `rcpt_domain` | Domain from RCPT TO | `example.com` |
| `is_tls` | Whether connection uses TLS | `true` or `false` |
| `helo_domain` | EHLO/HELO domain | `mail.example.com` |
| `asn` | Autonomous System Number | `15169` |
| `country` | Country code from GeoIP | `"US"` |

---

## Trusted Networks and Relay Hosts

### The Problem

When you have MX servers that relay mail to Stalwart, you don't want:
1. SPF checks performed on your own MX IPs (they'll fail)
2. Spam filtering applied to already-trusted mail
3. Rate limiting or other restrictions on internal relays

### The Solution: session.rcpt.relay

Stalwart provides the `session.rcpt.relay` configuration option to control which connections are allowed to relay mail.

**Default behavior** (`crates/common/src/config/smtp/session.rs:697-701`):
```rust
relay: IfBlock::new::<()>(
    "session.rcpt.relay",
    [("!is_empty(authenticated_as)", "true")],
    "false",
)
```

This means:
- If authenticated → allow relay
- Otherwise → deny relay

### How relay Works

Location: `crates/smtp/src/inbound/rcpt.rs:252-257`

When a RCPT TO command is received, Stalwart checks:
```rust
self.server.eval_if(
    &self.server.core.smtp.session.rcpt.relay,
    self,
    self.data.session_id,
).await
```

If `relay` evaluates to `true`, the recipient is accepted even if it's not a local domain.

---

## Disabling Spam Filtering for Trusted Relays

### Understanding Spam Filter Behavior

Location: `crates/smtp/src/inbound/spam.rs:38-44`

```rust
if !self.is_authenticated() {
    // Spam classification
    server.spam_filter_classify(&mut ctx).await
} else {
    // Trusted reply tracking (no filtering)
    server.spam_filter_analyze_reply_out(&mut ctx).await;
    SpamFilterAction::Allow(String::new())
}
```

**Key insight:** Authenticated sessions skip spam filtering automatically.

### Configuration Options

#### Option 1: Disable Spam Filter for Specific IPs

```toml
[session.data.spam-filter]

[[session.data.spam-filter.if]]
if = "remote_ip"
in-list = "trusted-relays"
then = "false"

[[session.data.spam-filter.else]]
then = "true"
```

Define your trusted relay IPs:
```toml
[lookup.trusted-relays]
10.0.0.0/8 = ""
192.168.1.0/24 = ""
172.16.0.0/12 = ""
203.0.113.10 = ""  # Your MX server IP
```

#### Option 2: Use Multiple Conditions

```toml
session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays')"
```

#### Option 3: Relay-Specific Configuration

```toml
# Allow relay from trusted IPs
session.rcpt.relay = "ip_in_list('remote_ip', 'trusted-relays') || !is_empty(authenticated_as)"

# Disable spam filter when relaying from trusted IPs
session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays')"
```

### Disabling SPF Checks

To prevent SPF checks on your trusted relay IPs, you can configure the SPF header addition:

```toml
# Only add SPF headers for non-trusted relays
session.data.add-headers.received-spf = "local_port == 25 && !ip_in_list('remote_ip', 'trusted-relays')"
```

---

## Practical Examples

### Example 1: Basic Trusted Relay Setup

**Scenario:** You have an MX at `203.0.113.10` that forwards to Stalwart. You want:
- No spam filtering
- No SPF checks
- Allow relay for any recipient

**Configuration:**

```toml
# Define trusted relays
[lookup.trusted-relays]
203.0.113.10 = ""

# Allow relay from trusted IPs
session.rcpt.relay = "ip_in_list('remote_ip', 'trusted-relays') || !is_empty(authenticated_as)"

# Disable spam filter for trusted relays
session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays')"

# Don't add SPF headers for trusted relays
session.data.add-headers.received-spf = "local_port == 25 && !ip_in_list('remote_ip', 'trusted-relays')"

# Don't add Received headers for trusted relays (optional)
session.data.add-headers.received = "local_port == 25 && !ip_in_list('remote_ip', 'trusted-relays')"
```

### Example 2: Multiple Trusted Networks

**Scenario:** You have multiple datacenters with different IP ranges.

```toml
[lookup.trusted-relays]
# Datacenter 1
10.1.0.0/16 = ""
# Datacenter 2
10.2.0.0/16 = ""
# Cloud provider
198.51.100.0/24 = ""
# Specific MX servers
203.0.113.10 = ""
203.0.113.11 = ""
203.0.113.12 = ""

session.rcpt.relay = "ip_in_list('remote_ip', 'trusted-relays') || !is_empty(authenticated_as)"
session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays')"
```

### Example 3: Port-Specific Behavior

**Scenario:** Port 25 accepts from trusted relays, ports 587/465 require authentication.

```toml
[lookup.trusted-relays]
203.0.113.0/24 = ""

# Complex relay logic
session.rcpt.relay = "(local_port == 25 && ip_in_list('remote_ip', 'trusted-relays')) || !is_empty(authenticated_as)"

# Spam filter only on port 25 from untrusted sources
session.data.spam-filter = "local_port == 25 && !ip_in_list('remote_ip', 'trusted-relays')"
```

### Example 4: Trusted Relay with Authentication Fallback

**Scenario:** Prefer trusted IPs but allow authenticated users from anywhere.

```toml
[lookup.trusted-relays]
203.0.113.0/24 = ""
10.0.0.0/8 = ""

# Allow relay from trusted IPs or authenticated users
session.rcpt.relay = "ip_in_list('remote_ip', 'trusted-relays') || !is_empty(authenticated_as)"

# Skip spam filter for trusted IPs or authenticated users
session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays') && is_empty(authenticated_as)"

# Only add auth headers for untrusted connections
session.data.add-headers.auth-results = "local_port == 25 && !ip_in_list('remote_ip', 'trusted-relays')"
```

### Example 5: Granular Control by Sender Domain

**Scenario:** Trust specific sender domains from specific IPs.

```toml
[lookup.trusted-relays]
203.0.113.10 = ""

[lookup.internal-domains]
example.com = ""
example.org = ""

# Complex condition
session.data.spam-filter = "!(ip_in_list('remote_ip', 'trusted-relays') && key_exists('internal-domains', sender_domain))"
```

---

## Configuration Loading and Precedence

### File Structure

Configuration is typically split across files:

```
resources/config/
├── config.toml          # Main configuration
├── smtp/
│   ├── session.toml     # SMTP session settings
│   ├── queue.toml       # Queue settings
│   └── spam.toml        # Spam filter rules
└── listeners.toml       # Network listeners
```

### How Configuration is Loaded

1. Main entry point: `crates/common/src/manager/boot.rs`
2. Parses TOML files in order
3. Builds configuration structures via `parse()` methods
4. Validates and reports errors

### Dynamic Reload

Stalwart supports configuration reloading without restart:
- HTTP API endpoint: `POST /api/reload`
- Most settings take effect immediately
- Some require service restart (like listener bindings)

---

## Common Expression Functions

### IP Functions

```toml
# Check if IP is in a list
ip_in_list('remote_ip', 'trusted-relays')

# Check if IP matches CIDR
matches_cidr('remote_ip', '192.168.0.0/16')
```

### String Functions

```toml
# String comparison
starts_with('sender_domain', 'trusted-')
ends_with('sender', '@example.com')
contains('helo_domain', 'mail')

# Regular expressions
matches('sender', '^no-reply@.*')
```

### Lookup Functions

```toml
# Key exists in lookup table
key_exists('blocked-domains', 'sender_domain')

# Get value from lookup
lookup('user-mapping', 'sender')
```

### Boolean Logic

```toml
# AND
is_tls && !is_empty(authenticated_as)

# OR
local_port == 587 || local_port == 465

# NOT
!ip_in_list('remote_ip', 'spammers')

# Complex
(local_port == 25 && ip_in_list('remote_ip', 'trusted-relays')) || !is_empty(authenticated_as)
```

---

## Debugging Configuration

### Check Configuration Syntax

```bash
# Stalwart validates configuration on startup
stalwart-mail --config /path/to/config.toml --check
```

### Enable Debug Logging

```toml
[tracer.stdout]
type = "stdout"
level = "debug"  # trace, debug, info, warn, error
enable = true
```

### Test Expressions

You can test expressions by examining logs during SMTP sessions. Look for events like:

```
[session.connect] remote_ip=203.0.113.10
[session.rcpt] relay=true reason="trusted relay"
[session.data] spam-filter=false reason="trusted relay"
```

### Common Issues

1. **Spam filter still running on trusted IPs**
   - Check: Is `session.data.spam-filter` evaluating correctly?
   - Verify: Is the IP in your `trusted-relays` lookup?
   - Test: Use `!is_empty(authenticated_as)` temporarily to verify logic

2. **Relay denied for trusted IPs**
   - Check: `session.rcpt.relay` configuration
   - Verify: IP matches exactly (including CIDR notation)

3. **SPF failures on internal mail**
   - Disable: `session.data.add-headers.received-spf` for trusted IPs
   - Or better: Skip spam filter entirely (it does SPF checks)

---

## Best Practices

### 1. Use Lookup Tables for IP Lists

Don't hardcode IPs in expressions:

❌ **Bad:**
```toml
session.rcpt.relay = "remote_ip == '203.0.113.10' || remote_ip == '203.0.113.11'"
```

✅ **Good:**
```toml
[lookup.trusted-relays]
203.0.113.10 = ""
203.0.113.11 = ""

session.rcpt.relay = "ip_in_list('remote_ip', 'trusted-relays')"
```

### 2. Document Your Configuration

Add comments explaining why rules exist:

```toml
# MX servers in production datacenter - no spam filtering needed
[lookup.trusted-relays]
203.0.113.0/24 = ""  # DC1 MX cluster
198.51.100.0/24 = "" # DC2 MX cluster
```

### 3. Test Changes Incrementally

Start with logging, then enforcement:

```toml
# Phase 1: Log only
session.data.spam-filter = "true"  # Still filter everything

# Phase 2: Disable for one IP
session.data.spam-filter = "remote_ip != '203.0.113.10'"

# Phase 3: Disable for all trusted
session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays')"
```

### 4. Secure Your Trusted Networks

Trusted networks bypass critical security checks. Ensure:
- IP ranges are as narrow as possible
- Networks are truly under your control
- Upstream relays perform their own filtering

### 5. Monitor for Abuse

Even trusted networks can be compromised:

```toml
# Still apply basic rate limiting to trusted relays
session.rcpt.max-recipients = "100"
session.data.limits.size = "104857600"  # 100MB
```

---

## Code Navigation Guide

For deeper understanding or modifications, here are key files:

### Configuration Parsing
- `crates/utils/src/config/parser.rs` - TOML parser
- `crates/utils/src/config/mod.rs` - Config trait and methods

### Expression Engine
- `crates/common/src/expr/if_block.rs` - IfBlock implementation
- `crates/common/src/expr/parser.rs` - Expression parser
- `crates/common/src/expr/eval.rs` - Expression evaluator
- `crates/common/src/expr/functions.rs` - Built-in functions

### SMTP Configuration
- `crates/common/src/config/smtp/session.rs` - Session config (includes relay)
- `crates/common/src/config/spamfilter.rs` - Spam filter config
- `crates/smtp/src/inbound/rcpt.rs` - RCPT command handler (relay check)
- `crates/smtp/src/inbound/spam.rs` - Spam classification logic
- `crates/smtp/src/inbound/data.rs` - DATA command handler

### Runtime Usage
- `crates/smtp/src/core/session.rs` - Session structure and methods
- `crates/smtp/src/inbound/*.rs` - SMTP command handlers

---

## Summary

**For your specific use case (trusted MX relays):**

1. **Define your trusted relay IPs:**
   ```toml
   [lookup.trusted-relays]
   203.0.113.0/24 = ""
   ```

2. **Allow relay from trusted IPs:**
   ```toml
   session.rcpt.relay = "ip_in_list('remote_ip', 'trusted-relays') || !is_empty(authenticated_as)"
   ```

3. **Disable spam filtering for trusted relays:**
   ```toml
   session.data.spam-filter = "!ip_in_list('remote_ip', 'trusted-relays')"
   ```

4. **Optional: Skip SPF header addition:**
   ```toml
   session.data.add-headers.received-spf = "local_port == 25 && !ip_in_list('remote_ip', 'trusted-relays')"
   ```

This configuration ensures your MX servers can relay through Stalwart without triggering spam checks or SPF validation failures.
