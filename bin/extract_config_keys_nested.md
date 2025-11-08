# Extract Stalwart Configuration Keys (Schema-based)

This document describes how to use the `extract_config_keys_nested.py` tool to automatically extract configuration keys from the Stalwart Mail Server source code by parsing serde struct definitions.

## Purpose

This tool uses a **schema-based approach** by analyzing Rust structs with `#[derive(Deserialize)]` to extract configuration keys. It's complementary to `extract_config_keys.py` which uses runtime pattern matching.

When running Stalwart, undocumented or obsolete keys are silently ignored. This tool extracts all keys directly from the Rust source tree, ensuring accuracy and transparency across versions.

You can use it to:
- Detect configuration changes between releases
- Understand the **type** of each configuration value
- Auto-generate verified documentation with type information
- Validate configuration files for unsupported keys
- Contribute accurate schema references to the FOSS community

## Approach Comparison

| Feature | extract_config_keys.py (Runtime) | extract_config_keys_nested.py (Schema) |
|---------|----------------------------------|----------------------------------------|
| Method | Searches for `config.property()` calls | Parses `struct` definitions with serde |
| Keys Found | Only actively used keys (572) | All struct-defined keys |
| Type Info | No | Yes (shows `String`, `bool`, etc.) |
| Dynamic Keys | Yes (`<id>` placeholders) | Limited (depends on struct definition) |
| False Positives | Very low | Possible (internal structs) |
| Best For | Ground truth of actual config | Schema and type information |

**Recommendation:** Run both and compare results for comprehensive documentation.

## Usage

```bash
# Clone a release of Stalwart
git clone https://github.com/stalwartlabs/mail-server.git
cd mail-server
git checkout v0.14.1

# Run the schema-based extractor (Markdown output)
/path/to/stalwart-scripts/extract_config_keys_nested.py ./crates > docs/config_keys_schema_0.14.1.md

# Or generate JSON output
/path/to/stalwart-scripts/extract_config_keys_nested.py ./crates --format json > docs/config_schema_0.14.1.json
```

Example output:

| Config Key | Type | Source |
|-------------|------|---------|
| `id` | `String` | `common/src/enterprise/llm.rs:21` |
| `api_type` | `ApiType` | `common/src/enterprise/llm.rs:22` |
| `url` | `String` | `common/src/enterprise/llm.rs:23` |
| `model` | `String` | `common/src/enterprise/llm.rs:24` |
| `timeout` | `Duration` | `common/src/enterprise/llm.rs:25` |
| `headers` | `HeaderMap` | `common/src/enterprise/llm.rs:26` |
| `tls_allow_invalid_certs` | `bool` | `common/src/enterprise/llm.rs:27` |
| `default_temperature` | `f64` | `common/src/enterprise/llm.rs:28` |
| `verify` | `IfBlock` | `common/src/config/smtp/auth.rs:59` |
| `verify.key` | `String` | `common/src/expr/if_block.rs:26` |
| `verify.if_then` | `Vec<IfThen>` | `common/src/expr/if_block.rs:27` |
| `verify.if_then.expr` | `Expression` | `common/src/expr/if_block.rs:20` |
| `verify.if_then.then` | `Expression` | `common/src/expr/if_block.rs:21` |

## How It Works

### Pass 1: Struct Collection
Scans all `.rs` files for public structs and their fields, collecting:
- Struct names and field definitions
- Serde attributes:
  - `#[serde(rename = "...")]` - Custom key names
  - `#[serde(flatten)]` - Embedded struct fields

### Pass 2: Recursive Expansion
For each struct, recursively expands nested types:
- `Option<ServerConfig>` → looks up `ServerConfig` struct
- `Vec<ListenerConfig>` → looks up `ListenerConfig` struct
- Handles flattened structs by merging fields at same level

### Pass 3: Root Discovery
Finds actual configuration entry points by searching for:
- `StructName::parse()` calls
- `from_str::<StructName>` patterns
- `deserialize::<StructName>` patterns

Falls back to name-based heuristic (`*Config` structs) if no patterns found.

### Pass 4: Output Generation
Produces either:
- **Markdown table** with key, type, and source location
- **JSON** with structured schema information

## Limitations

This schema-based approach has some known limitations:

1. **Dynamic Keys Not Detected**: Keys constructed at runtime like `queue.connection.<id>` may appear without the `<id>` placeholder, or may be split across multiple entries.

2. **Internal Structs**: May include structs used internally that aren't actually exposed as configuration options.

3. **Incomplete Type Info**: Generic types like `IfBlock` or `Expression` don't show the actual value types expected.

4. **No Default Values**: Unlike runtime analysis, this approach doesn't capture default values from the code.

**Recommendation**: Use `extract_config_keys.py` as the authoritative source, and use this tool to supplement with type information.

## Combining Both Approaches

For comprehensive documentation, run both tools and compare:

```bash
# Runtime approach (ground truth)
python3 extract_config_keys.py stalwart --format flat | sort > keys_runtime.txt

# Schema approach (type information)
python3 extract_config_keys_nested.py stalwart/crates 2>/dev/null | \
    grep '`' | cut -d'`' -f2 | sort > keys_schema.txt

# Keys in runtime but not schema (dynamically constructed)
comm -23 keys_runtime.txt keys_schema.txt

# Keys in schema but not runtime (potentially unused)
comm -13 keys_runtime.txt keys_schema.txt

# Keys in both (verified with type info)
comm -12 keys_runtime.txt keys_schema.txt
```

## Version Comparison

Compare configuration changes between releases:

```bash
# Extract from two versions
python3 extract_config_keys_nested.py stalwart-0.13.1/crates > config_0.13.1.md
python3 extract_config_keys_nested.py stalwart-0.14.1/crates > config_0.14.1.md

# Generate diff
diff -u config_0.13.1.md config_0.14.1.md > config_changes_0.13_to_0.14.md
```

## Contributing

Ideas for future enhancements:
- Parse default values from `#[serde(default = "fn_name")]`
- Better handling of generic types to show actual value types
- Detect and mark deprecated fields from comments
- Integration with documentation generators
- GitHub Actions workflow for automatic extraction on new releases

## License

Released under the MIT License. 
