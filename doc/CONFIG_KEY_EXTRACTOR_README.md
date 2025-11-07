# Stalwart Configuration Key Extractor

A utility to discover all possible configuration keys in the Stalwart Mail Server by analyzing its Rust source code.

## Problem Statement

Stalwart's configuration system uses a dynamic key-based approach where configuration keys are accessed programmatically rather than defined in traditional serialization structs. This makes it difficult to know all available configuration options just by reading documentation or examining a sample `config.toml` file.

For example, the key `queue.tls.default.dane` might not appear in your config file, but it's a valid configuration option that Stalwart will recognize and use.

## Solution

This Python utility (`extract_config_keys.py`) scans the Stalwart Rust source code to find all places where configuration keys are accessed and builds a comprehensive list of available keys.

## What It Finds

The utility discovers configuration keys by analyzing patterns like:

- `config.property("key.path")` - Simple property access
- `config.value(("key", "subkey", "leaf"))` - Tuple-based key access
- `config.sub_keys("base.key", ".suffix")` - Dynamic key discovery
- `config.sub_keys_with_suffixes("base.key", &[".suffix1", ".suffix2"])` - Multiple suffix patterns
- `config.values("key.path")` - Array value access

## Usage

### Basic Usage

```bash
# Show all keys in tree format (default)
python3 extract_config_keys.py

# Show all keys as flat list
python3 extract_config_keys.py --format flat

# Export to JSON
python3 extract_config_keys.py --format json --output config_keys.json

# Filter keys by prefix
python3 extract_config_keys.py --filter queue --format flat
python3 extract_config_keys.py --filter server.listener --format tree
```

### Command Line Options

```
Usage: extract_config_keys.py [OPTIONS] [SOURCE_DIR]

Arguments:
  SOURCE_DIR          Path to Stalwart source directory (default: current directory)

Options:
  --format FORMAT     Output format: tree, flat, or json (default: tree)
  --output FILE       Output file for JSON format
  --filter PREFIX     Filter keys by prefix (e.g., "queue" or "server.listener")
  --help              Show help message
```

## Output Formats

### Tree Format

Displays keys in a hierarchical tree structure:

```
├── queue
│   ├── connection
│   │   └── <id>
│   │       ├── ehlo-hostname
│   │       └── timeout
│   │           ├── connect
│   │           ├── data
│   │           └── ehlo
│   ├── tls
│   │   └── <id>
│   │       ├── dane
│   │       ├── starttls
│   │       └── allow-invalid-certs
```

### Flat Format

Simple newline-separated list of full key paths:

```
queue.connection
queue.connection.<id>.ehlo-hostname
queue.connection.<id>.timeout.connect
queue.tls
queue.tls.<id>.dane
queue.tls.<id>.starttls
```

### JSON Format

Structured JSON with:
- `keys`: Array of all discovered keys
- `hierarchy`: Nested object representation
- `contexts`: Source file locations and access patterns for each key

## Understanding `<id>` Placeholders

Keys containing `<id>` are template keys that support user-defined identifiers. For example:

- `queue.tls.<id>.dane` means you can define:
  - `queue.tls.default.dane = "optional"`
  - `queue.tls.strict.dane = "require"`
  - `queue.tls.my-custom-policy.dane = "disable"`

The `<id>` can be any valid identifier you choose, and you reference it in your configuration logic.

## Examples

### Example 1: Find all queue-related keys

```bash
$ python3 extract_config_keys.py --filter queue --format flat

queue.connection
queue.connection.<id>.ehlo-hostname
queue.connection.<id>.timeout.connect
queue.connection.<id>.timeout.data
queue.connection.<id>.timeout.ehlo
queue.connection.<id>.timeout.greeting
queue.connection.<id>.timeout.mail-from
queue.connection.<id>.timeout.rcpt-to
queue.route
queue.route.<id>.type
queue.route.address
queue.route.auth.secret
queue.route.auth.username
queue.schedule
queue.schedule.<id>.expire
queue.schedule.<id>.max-attempts
queue.schedule.<id>.notify
queue.schedule.<id>.queue-name
queue.schedule.<id>.retry
queue.tls
queue.tls.<id>.allow-invalid-certs
queue.tls.<id>.dane
queue.tls.<id>.starttls
queue.tls.<id>.timeout.mta-sts
queue.tls.<id>.timeout.tls
queue.virtual
queue.virtual.<id>.threads-per-node
```

### Example 2: Explore server listener configuration

```bash
$ python3 extract_config_keys.py --filter server.listener --format tree

└── server
    └── listener
        ├── <id>
        │   └── protocol
        └── protocol
```

### Example 3: Export all keys to JSON for programmatic use

```bash
$ python3 extract_config_keys.py --format json --output config_keys.json

$ jq '.keys | length' config_keys.json
173

$ jq '.contexts["queue.tls.<id>.dane"]' config_keys.json
[
  {
    "file": "common/src/config/smtp/queue.rs",
    "type": "sub_keys_with_suffixes_template"
  }
]
```

## Statistics

As of the last scan:
- **173 unique configuration keys** discovered
- **797 Rust files** analyzed
- Includes both concrete keys and template keys with `<id>` placeholders

## Interpreting Results

### Key Types

The JSON output includes context information showing how each key was discovered:

- `string`: Accessed via simple string like `config.property("key.path")`
- `tuple`: Accessed via tuple like `config.property(("key", "subkey"))`
- `sub_keys`: Base key for dynamic discovery
- `sub_keys_template`: Template key derived from suffix patterns
- `sub_keys_with_suffixes`: Base key with multiple suffix patterns
- `sub_keys_with_suffixes_template`: Template key from multiple suffixes
- `values`: Array-based configuration

### Limitations

This tool finds keys that are **programmatically accessed** in the code. It may not find:
- Keys that are only documented but not yet implemented
- Keys that are constructed dynamically at runtime
- Deprecated keys that are no longer referenced in the code
- Some complex configuration patterns that use variables

However, it will find all keys that Stalwart actually uses in its configuration parsing logic.

## Use Cases

1. **Configuration Exploration**: Discover what configuration options are available
2. **Documentation**: Generate reference documentation for configuration keys
3. **Validation**: Build config file validators that check for typos
4. **IDE Support**: Create autocomplete data for editors
5. **Migration Tools**: Identify configuration differences between versions

## How It Works

The utility uses regular expressions to parse Rust source files and find patterns where the `config` object is used to access configuration values. It specifically looks for:

1. Direct property/value access patterns
2. Sub-key discovery patterns that indicate dynamic configuration sections
3. Suffix-based patterns that generate template keys

The tool then:
1. Normalizes the discovered keys
2. Builds a hierarchical representation
3. Tracks source locations for each key
4. Exports in your chosen format

## Contributing

If you find configuration keys that should be included but are missing, or if you encounter parsing errors, please examine the patterns in `extract_config_keys.py` and submit improvements.

## License

This utility follows the same license as the Stalwart Mail Server project.

## See Also

- [Stalwart Mail Server Documentation](https://stalw.art/docs/)
- [Stalwart GitHub Repository](https://github.com/stalwartlabs/mail-server)
