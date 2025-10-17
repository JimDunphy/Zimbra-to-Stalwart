# Stalwart Configuration Viewer - Examples

## Quick Start

The `list_config.sh` script provides an easy way to view Stalwart configuration via the Management API.

### Basic Setup

```bash
# Set your environment variables (optional)
export STALWART_URL="https://mail.example.com"
export STALWART_USER="admin"
export STALWART_PASS="your-password"

# Or use command-line arguments
./list_config.sh --url https://mail.example.com --user admin --password your-password
```

## Common Use Cases

### 1. List All Configuration Keys

```bash
# List everything (will prompt for password if not set)
./list_config.sh --list

# Output:
# Configuration Keys
#
# Total keys: 247
#
# oauth.key = 3p6GvM2k...
# queue.connection.default.description = Default connection settings
# queue.connection.default.timeout.connect = 5m
# queue.limiter.inbound.ip.enable = true
# queue.limiter.inbound.ip.key = remote_ip
# ...
```

### 2. Filter by Prefix

```bash
# List all queue configuration
./list_config.sh --list queue

# List all server configuration
./list_config.sh --list server

# List all TLS-related queue settings
./list_config.sh --list queue.tls
```

### 3. Get Specific Keys

```bash
# Get single key
./list_config.sh --get storage.data

# Get multiple keys (comma-separated)
./list_config.sh --get storage.data,storage.blob,server.hostname

# Output:
# Configuration Values
#
# storage.data [local]
#   rocksdb
#
# storage.blob [local]
#   rocksdb
#
# server.hostname [database]
#   mail.example.com
```

### 4. Get All Keys with Prefix

```bash
# Get all queue.tls.* keys
./list_config.sh --prefix queue.tls

# Get multiple prefixes
./list_config.sh --prefix "queue.tls,queue.schedule"
```

### 5. Group Related Configuration

Very useful for viewing policies/strategies that have multiple sub-keys:

```bash
# Group all TLS policies
./list_config.sh --group queue.tls --suffix dane

# Output:
# Grouped Configuration
#
# Total items: 2
#
# [default]
#   allow-invalid-certs = false
#   dane = optional
#   description = Default TLS settings
#   starttls = optional
#
# [invalid-tls]
#   allow-invalid-certs = true
#   dane = disable
#   description = Allow invalid TLS certificates
#   starttls = optional

# Group queue schedules
./list_config.sh --group queue.schedule --suffix retry

# Group virtual queues
./list_config.sh --group queue.virtual --suffix threads-per-node
```

### 6. Raw JSON Output

Perfect for piping to other tools:

```bash
# Get raw JSON
./list_config.sh --list queue --json

# Pipe to jq for custom processing
./list_config.sh --list queue --json | jq '.data.items | keys'

# Count configuration keys
./list_config.sh --list --json | jq '.data.total'

# Find keys containing "tls"
./list_config.sh --list --json | jq '.data.items | keys[] | select(contains("tls"))'
```

## Practical Examples

### Audit Your Queue Configuration

```bash
#!/bin/bash
echo "=== Queue Virtual Queues ==="
./list_config.sh --group queue.virtual --suffix threads-per-node

echo -e "\n=== Queue Schedules ==="
./list_config.sh --group queue.schedule --suffix retry

echo -e "\n=== Queue TLS Policies ==="
./list_config.sh --group queue.tls --suffix dane

echo -e "\n=== Queue Routes ==="
./list_config.sh --group queue.route --suffix type
```

### Find All Storage Configuration

```bash
./list_config.sh --prefix "storage,store" --json | jq -r '.data | to_entries[] | "\(.key) = \(.value)"'
```

### Compare Local vs Database Keys

```bash
# List all server.* (should be local)
./list_config.sh --list server

# List all queue.* (should be database)
./list_config.sh --list queue
```

### Export Configuration to File

```bash
# Export all configuration as JSON
./list_config.sh --list --json > stalwart_config_backup.json

# Export specific section
./list_config.sh --list queue --json > queue_config.json

# Export as simple key=value pairs
./list_config.sh --list --json | jq -r '.data.items | to_entries[] | "\(.key)=\(.value)"' > config.env
```

### Check Specific Settings

```bash
# Check TLS configuration for a specific policy
./list_config.sh --get queue.tls.default.dane,queue.tls.default.starttls,queue.tls.default.allow-invalid-certs

# Check what store is being used
./list_config.sh --get storage.data,storage.blob,storage.lookup,storage.fts

# Check SMTP session limits
./list_config.sh --prefix session.throttle
```

## Advanced Usage

### Using with Watch for Real-Time Monitoring

```bash
# Watch configuration changes every 2 seconds
watch -n 2 './list_config.sh --list queue.limiter --json | jq ".data.items"'
```

### Diff Configuration Between Servers

```bash
# Server 1
STALWART_URL=https://mail1.example.com ./list_config.sh --list queue --json | jq -S . > server1.json

# Server 2
STALWART_URL=https://mail2.example.com ./list_config.sh --list queue --json | jq -S . > server2.json

# Compare
diff -u server1.json server2.json
```

### Check for Missing Configuration

```bash
#!/bin/bash
# Check if critical queue settings exist

critical_keys=(
    "queue.schedule.remote.retry.0"
    "queue.schedule.remote.expire"
    "queue.tls.default.dane"
    "queue.route.mx.type"
)

for key in "${critical_keys[@]}"; do
    result=$(./list_config.sh --get "$key" --json 2>/dev/null | jq -r ".data.\"$key\"")
    if [ "$result" = "null" ] || [ -z "$result" ]; then
        echo "⚠️  Missing: $key"
    else
        echo "✓ Found: $key = $result"
    fi
done
```

### Extract and Apply Configuration

```bash
# Extract a specific configuration section
./list_config.sh --prefix queue.tls --json | \
    jq '.data' > queue_tls_config.json

# You can then use this with the Management API to apply to another server
# (requires additional scripting for POST operations)
```

## Understanding the Output Colors

The script color-codes keys based on where they should be stored:

- **Yellow + [local]** - Keys that belong in `config.toml`
  - `store.*`, `directory.*`, `server.*`, `certificate.*`, `tracer.*`, `storage.*`

- **Green + [database]** - Keys that belong in the database
  - `queue.*`, `session.*`, `jmap.*`, `spam-filter.*`, `sieve.*`

If you see mismatched colors (e.g., a `queue.*` key marked as `[local]`), you might have configuration in the wrong place!

## Troubleshooting

### Authentication Errors

```bash
# HTTP 401 - Bad credentials
Error: HTTP 401
"Authentication failed"

# Solution: Check username/password
./list_config.sh --user admin --password correct-password --list
```

### Connection Errors

```bash
# Can't connect to server
curl: (7) Failed to connect to localhost port 8080

# Solution: Check URL and ensure server is running
./list_config.sh --url http://localhost:8080 --list
```

### Missing jq

```bash
# Error: jq is required but not installed

# Install on Ubuntu/Debian
sudo apt install jq

# Install on macOS
brew install jq

# Install on RHEL/CentOS
sudo yum install jq
```

### Empty Results

If you get no results, the prefix might be wrong or no keys exist:

```bash
# Check without prefix first
./list_config.sh --list

# Then gradually narrow down
./list_config.sh --list queue
./list_config.sh --list queue.tls
```

## API Endpoints Used

The script uses these Stalwart Management API endpoints:

1. **`GET /api/settings/list?prefix=<prefix>`**
   - Lists all configuration keys with optional prefix filter
   - Returns: `{ "data": { "total": N, "items": { "key": "value", ... }}}`

2. **`GET /api/settings/keys?keys=<key1,key2>&prefixes=<prefix1,prefix2>`**
   - Gets specific keys or all keys with prefixes
   - Returns: `{ "data": { "key": "value", ... }}`

3. **`GET /api/settings/group?prefix=<prefix>&suffix=<suffix>`**
   - Groups related configuration by ID
   - Returns: `{ "data": { "total": N, "items": [{ "_id": "...", "field": "value", ...}]}}`

## Script Options Reference

```
-u, --url URL          Stalwart server URL (default: http://localhost:8080)
-a, --user USER        Admin username (default: admin)
-p, --password PASS    Admin password (or set STALWART_PASS env var)
-l, --list [PREFIX]    List all config keys with optional prefix filter
-g, --get KEYS         Get specific keys (comma-separated)
-P, --prefix PREFIXES  Get all keys with prefixes (comma-separated)
-G, --group PREFIX     Group keys by prefix (e.g., queue.tls)
-s, --suffix SUFFIX    Suffix for grouping (used with --group)
-j, --json             Output raw JSON
-t, --tree             Display in tree format (default for --list)
-h, --help             Show help message
```

## Security Notes

⚠️ **Password Security:**
- Avoid passing passwords via command line (visible in process list)
- Prefer environment variables: `export STALWART_PASS=password`
- Or let the script prompt you interactively (most secure)

⚠️ **HTTPS:**
- Always use HTTPS in production: `--url https://mail.example.com`
- For local development with self-signed certs, you may need to add `-k` to curl in the script

## Integration with Other Tools

### Shell Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
alias sconfig='~/stalwart/list_config.sh'
alias sconfig-queue='sconfig --list queue'
alias sconfig-tls='sconfig --group queue.tls --suffix dane'
```

### Monitoring Scripts

```bash
#!/bin/bash
# monitor_config.sh - Alert on configuration changes

LAST_HASH_FILE="/tmp/stalwart_config_hash"
CURRENT_HASH=$(./list_config.sh --list --json | sha256sum | cut -d' ' -f1)

if [ -f "$LAST_HASH_FILE" ]; then
    LAST_HASH=$(cat "$LAST_HASH_FILE")
    if [ "$CURRENT_HASH" != "$LAST_HASH" ]; then
        echo "⚠️  Configuration changed!"
        # Send alert (email, Slack, etc.)
    fi
fi

echo "$CURRENT_HASH" > "$LAST_HASH_FILE"
```

## See Also

- `CONFIG_STORAGE_EXPLAINED.md` - Detailed explanation of Stalwart's configuration system
- `extract_config_keys.md` - Tool for discovering all possible configuration keys
- [Stalwart Management API Documentation](https://stalw.art/docs/api/)
