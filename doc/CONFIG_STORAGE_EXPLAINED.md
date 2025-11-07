# Stalwart Configuration Storage: config.toml vs RocksDB

## Your Question

> If one was using RocksDB for everything (default), could we find the values for these keys by doing `stalwart-cli server list-config`? Or do they also have an in-memory version that might not be in sync? The entire how they load from config.toml to RocksDB has always confused me where one can get these warnings that things are out of sync.

## TL;DR Answer

**Yes, you can retrieve configuration values**, but it's more complex than it seems. Stalwart uses a **two-tier configuration system**:

1. **Local Configuration** (`config.toml`) - File-based, for infrastructure settings
2. **Database Configuration** (RocksDB/etc.) - Store-based, for dynamic settings

They are NOT "out of sync" in the traditional sense - they are **intentionally separate** with different purposes. The warnings occur when keys are defined in the wrong place.

## The Two-Tier Configuration System

### Configuration Storage Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Stalwart Server                       │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │           In-Memory Configuration                   │ │
│  │         (Merged from both sources)                  │ │
│  └────────────────────────────────────────────────────┘ │
│           ▲                            ▲                 │
│           │                            │                 │
│  ┌────────┴────────┐         ┌────────┴─────────┐      │
│  │  cfg_local      │         │   cfg_store       │      │
│  │  (config.toml)  │         │   (RocksDB)       │      │
│  │  ArcSwap<Map>   │         │   Store handle    │      │
│  └─────────────────┘         └───────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### What Goes Where?

The system determines which keys belong in which storage using **patterns** defined by `config.local-keys.*` or defaults.

#### Default Local Keys (config.toml)

From `crates/common/src/manager/config.rs:520-540`:

```rust
Pattern::Include(MatchType::StartsWith("store.".to_string())),
Pattern::Include(MatchType::StartsWith("directory.".to_string())),
Pattern::Include(MatchType::StartsWith("tracer.".to_string())),
Pattern::Exclude(MatchType::StartsWith("server.blocked-ip.".to_string())),
Pattern::Exclude(MatchType::StartsWith("server.allowed-ip.".to_string())),
Pattern::Include(MatchType::StartsWith("server.".to_string())),
Pattern::Include(MatchType::StartsWith("certificate.".to_string())),
Pattern::Include(MatchType::StartsWith("config.local-keys.".to_string())),
Pattern::Include(MatchType::StartsWith("authentication.fallback-admin.".to_string())),
Pattern::Include(MatchType::StartsWith("cluster.".to_string())),
Pattern::Include(MatchType::Equal("storage.data".to_string())),
Pattern::Include(MatchType::Equal("storage.blob".to_string())),
Pattern::Include(MatchType::Equal("storage.lookup".to_string())),
Pattern::Include(MatchType::Equal("storage.fts".to_string())),
Pattern::Include(MatchType::Equal("storage.directory".to_string())),
Pattern::Include(MatchType::Equal("enterprise.license-key".to_string())),
```

**Local keys are for:**
- Database connection settings (`store.*`)
- Server listeners and network config (`server.*`)
- Directories (`directory.*`)
- Certificates (`certificate.*`)
- Tracing/logging (`tracer.*`)
- Storage backend selection (`storage.{data,blob,lookup,fts}`)
- Fallback admin credentials
- Cluster configuration

**Why local?** These are infrastructure settings that:
- Must be available before the database is initialized
- Should survive database failures
- Need to be version-controlled alongside the server deployment
- Rarely change

#### Database Keys (RocksDB)

Everything else goes in the database, including:
- Queue configuration (`queue.*`)
- SMTP settings (`session.*`, `queue.*`)
- JMAP settings (`jmap.*`)
- Spam filter rules (`spam-filter.*`)
- DKIM keys (`dkim.*`)
- User accounts and domains
- Dynamic policies and rules

**Why database?** These are dynamic settings that:
- Can be changed without restarting the server
- Can be managed via the web admin interface
- Can be different across clustered nodes
- Change frequently

## The Boot Process

Here's what happens when Stalwart starts (from `crates/common/src/manager/boot.rs`):

### Step 1: Read Local Configuration
```rust
let cfg_local_path = PathBuf::from(config_path.unwrap());
let mut config = Config::default();
match std::fs::read_to_string(&cfg_local_path) {
    Ok(value) => {
        config.parse(&value).failed("Invalid configuration file");
    }
    // ...
}
let cfg_local = config.keys.clone();
```

### Step 2: Parse Stores (Using Local Config)
```rust
let mut stores = Stores::parse(&mut config).await;
let local_patterns = Patterns::parse(&mut config);
```

### Step 3: Build ConfigManager
```rust
let manager = ConfigManager {
    cfg_local: ArcSwap::from_pointee(cfg_local),
    cfg_local_path,
    cfg_local_patterns: local_patterns.into(),
    cfg_store: config
        .value("storage.data")
        .and_then(|id| stores.stores.get(id))
        .cloned()
        .unwrap_or_default(),
};
```

### Step 4: Extend with Database Configuration
```rust
// Extend configuration with settings stored in the db
if !manager.cfg_store.is_none() {
    for (key, value) in manager
        .db_list("", false)
        .await
        .failed("Failed to read database configuration")
    {
        if manager.cfg_local_patterns.is_local_key(&key) {
            config.new_build_warning(
                &key,
                concat!(
                    "Local key defined in database, this might cause issues. ",
                    "See https://stalw.art/docs/configuration/overview/#loc",
                    "al-and-database-settings"
                ),
            );
        }

        config.keys.entry(key).or_insert(value);
    }
}
```

**Key insight:** Database keys are added with `or_insert`, meaning **local config takes precedence** if a key exists in both places!

### Step 5: Warnings About Misplaced Keys

From `crates/common/src/manager/boot.rs:270-286`:

```rust
// Build local keys and warn about database keys defined in the local configuration
let mut warn_keys = Vec::new();
for key in config.keys.keys() {
    if !local_patterns.is_local_key(key) {
        warn_keys.push(key.clone());
    }
}
for warn_key in warn_keys {
    config.new_build_warning(
        warn_key,
        concat!(
            "Database key defined in local configuration, this might cause issues. ",
            "See https://stalw.art/docs/configuration/overview/#loc",
            "al-and-database-settings"
        ),
    );
}
```

**This is where the "out of sync" warnings come from!**

If you define `queue.tls.default.dane = "require"` in `config.toml`, you'll get a warning because:
1. `queue.*` keys should be in the database
2. Having it in local config means it won't be editable via web admin
3. It won't sync across cluster nodes via the database
4. It can cause confusion when the same key exists in both places

## Retrieving Configuration Values

### Via Management API

The web admin and CLI use the management API endpoints (from `crates/http/src/management/settings.rs`):

#### List All Configuration

**Endpoint:** `GET /api/settings/list?prefix=queue.`

**Code:**
```rust
let settings = self.core.storage.config.list(&prefix, true).await?;
```

This calls `ConfigManager::list()` which:
1. Queries the database with `db_list(prefix, strip_prefix)`
2. Merges with local config keys
3. Returns the combined result

#### Get Specific Keys

**Endpoint:** `GET /api/settings/keys?keys=queue.tls.default.dane&prefixes=queue.schedule`

**Code:**
```rust
for key in keys {
    if let Some(value) = self.core.storage.config.get(key).await? {
        results.insert(key.to_string(), value);
    }
}
```

This calls `ConfigManager::get()` which:
```rust
pub async fn get(&self, key: impl AsRef<str>) -> trc::Result<Option<String>> {
    let key = key.as_ref();
    match self.cfg_local.load().get(key) {
        Some(value) => Ok(Some(value.to_string())),  // Local takes precedence!
        None => {
            self.cfg_store
                .get_value(ValueKey::from(ValueClass::Config(
                    key.to_string().into_bytes(),
                )))
                .await
        }
    }
}
```

**Order of precedence:**
1. Check local config first
2. If not found, check database
3. Return None if in neither

### Via CLI (If It Were Implemented)

The CLI structure in `crates/cli/` shows support for:
- `Import` / `Export` - Full data backup/restore
- `Server` commands - Server management
- `Queue` / `Report` / `DKIM` - Specific subsystem management

However, I don't see a `server list-config` command implemented. The CLI would likely use the same management API endpoints.

## The "In-Memory" Configuration

There is an in-memory representation, but it's NOT a third separate source - it's the **merged view**:

### ConfigManager Structure
```rust
pub struct ConfigManager {
    pub cfg_local: ArcSwap<BTreeMap<String, String>>,  // In-memory local config
    pub cfg_local_path: PathBuf,                        // Path to config.toml
    pub cfg_local_patterns: Arc<Patterns>,              // Patterns for key classification
    pub cfg_store: Store,                               // Database handle
}
```

### How Config is Retrieved

When code asks for a configuration value:

```rust
// Example from your concern about queue.tls
config.property(("queue.tls", id, "dane"))
```

This internally calls `Config::keys.get()` which accesses the **merged map** built during startup:
1. Starts with local config
2. Extended with database config (using `entry().or_insert()`)
3. Used throughout the server's lifetime

### Config Reload

From `crates/http/src/management/reload.rs:74-82`:

```rust
let result = self.reload().await?;
if !UrlParams::new(req.uri().query()).has_key("dry-run") {
    if let Some(core) = result.new_core {
        // Update core
        self.inner.shared_core.store(core.into());

        self.cluster_broadcast(BroadcastEvent::ReloadSettings).await;
    }
    // ...
}
```

When you reload configuration:
1. Reads `config.toml` again
2. Reads database again
3. Merges them (local takes precedence)
4. Replaces the `shared_core` with new configuration via `ArcSwap`
5. Broadcasts reload event to cluster

**The in-memory config IS always in sync** because it's rebuilt from both sources on every reload.

## Answer to Your Specific Questions

### 1. Can we find values using RocksDB when using it for everything?

**Yes**, via the management API endpoints:
- `GET /api/settings/list?prefix=queue.` - List all queue.* keys
- `GET /api/settings/keys?keys=queue.tls.default.dane` - Get specific key
- `GET /api/settings/group?prefix=queue.tls&suffix=dane` - Group related keys

These APIs call `ConfigManager::list()` and `ConfigManager::get()` which merge local and database config.

### 2. Is there an in-memory version that might not be in sync?

**No, not really.** The "in-memory" version is:
- Built during startup by merging local + database
- Rebuilt during reload by merging local + database
- Always represents the current effective configuration

What CAN be "out of sync":
1. **Local config file vs database** - Intentionally separate! Different purposes.
2. **Running config vs config file** - Until you reload
3. **Cluster nodes** - Brief sync delay when one node updates database keys

### 3. Where do the "out of sync" warnings come from?

They're warnings about **misplaced keys**, not sync issues:

**Warning 1: Database key in local config**
```
Database key defined in local configuration, this might cause issues.
```

You put `queue.tls.default.dane = "require"` in `config.toml`, but:
- `queue.*` keys belong in the database
- It won't be manageable via web admin
- It won't sync across cluster nodes
- Changes require file edit + reload instead of just API call

**Warning 2: Local key in database**
```
Local key defined in database, this might cause issues.
```

You put `server.listener.smtp.bind = "[::]:25"` in the database, but:
- `server.*` keys belong in local config
- They're needed before database is available
- They should be version-controlled
- If the database is corrupted/lost, the server won't know how to listen

## Best Practices

### ✅ DO: Put in config.toml
- `store.*` - Database connections
- `server.*` - Listeners, network settings
- `directory.*` - Directory configurations
- `certificate.*` - TLS certificates
- `tracer.*` - Logging configuration
- `storage.{data,blob,lookup,fts}` - Storage backend selection
- `authentication.fallback-admin.*` - Emergency admin account

### ✅ DO: Put in Database (via web admin or API)
- `queue.*` - Queue and delivery settings
- `session.*` - SMTP session settings
- `jmap.*` - JMAP protocol settings
- `spam-filter.*` - Spam filter rules
- `sieve.*` - Sieve scripts
- User accounts, domains, aliases
- DKIM keys
- Rate limiters and quotas

### ❌ DON'T: Mix Them

Don't define database keys in `config.toml` unless you have a specific reason and understand the implications.

## How to List All Effective Configuration

### Option 1: Management API (Recommended)

```bash
# List all configuration with prefix
curl -u "admin:password" "https://mail.example.com/api/settings/list"

# List specific prefix
curl -u "admin:password" "https://mail.example.com/api/settings/list?prefix=queue"

# Get specific keys
curl -u "admin:password" "https://mail.example.com/api/settings/keys?keys=queue.tls.default.dane,storage.data"
```

### Option 2: Direct Database Query (Advanced)

If you really want to see raw database config:

```bash
# Using the store console
stalwart-mail --console --config /etc/stalwart/config.toml

# Then query the Config key-value store
# (This requires understanding Stalwart's internal storage format)
```

### Option 3: Reload with Inspection

```bash
# Trigger reload and inspect returned config
curl -u "admin:password" "https://mail.example.com/api/reload"
```

The reload response includes the merged configuration that was loaded.

## Summary

1. **Two storage tiers** - Local file (infrastructure) and database (dynamic settings)
2. **Merged at startup** - Combined into in-memory map, local takes precedence
3. **Always in sync** - In-memory is rebuilt from both sources on reload
4. **"Out of sync" warnings** - Actually about keys being in the wrong tier
5. **Retrievable via API** - Management API endpoints give you effective configuration
6. **Reload updates both** - Rereads file and database, merges, updates running config

The confusion is understandable because this two-tier approach is unusual, but it's intentional and well-designed for Stalwart's use case of being both a file-configured server and a dynamically-managed mail platform.

## References

- `crates/common/src/manager/config.rs` - ConfigManager implementation
- `crates/common/src/manager/boot.rs` - Boot process and warning generation
- `crates/http/src/management/settings.rs` - Management API for config retrieval
- `crates/http/src/management/reload.rs` - Config reload implementation
