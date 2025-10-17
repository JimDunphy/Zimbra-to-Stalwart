# Configuration Key Extractor for Stalwart Mail Server

## Overview

This utility extracts and displays **all possible configuration keys** from the Stalwart Mail Server source code. It provides a comprehensive view of available configuration options, addressing the confusion around undocumented keys like `queue.outbound.tls`.

## Important Note

**This tool discovers configuration KEY names only, not their values.**

It shows you *what* keys exist and their hierarchical structure, but does not extract:
- Default values
- Valid value types
- Value constraints or validation rules
- Documentation or descriptions

Think of it as discovering the schema or structure of the configuration file, not the actual configuration data.

## The Problem

Stalwart's configuration system uses a dynamic, code-based approach where configuration keys are accessed programmatically rather than defined in traditional serialization structs (like Serde Deserialize). This makes it difficult to know all available configuration options just by reading documentation or examining a sample `config.toml` file.

For example, you might wonder: "Does `queue.tls.default.dane` exist?" The documentation may not mention it, and it might not be in your config file, but it could be a valid configuration option that Stalwart recognizes and uses.

## The Solution

The **Configuration Key Extractor** (`extract_config_keys.py`) scans the Stalwart Rust source code to find all places where configuration keys are accessed and builds a comprehensive list of available keys, presented in a tree layout for easy exploration.

## What Was Created

### 1. `extract_config_keys.py`

A Python utility that:
- Scans all Rust source files in the Stalwart codebase (797 files)
- Uses regex patterns to find configuration key access patterns
- Discovers **173 unique configuration keys** including template keys
- Supports three output formats: **tree**, **flat**, and **JSON**
- Can filter keys by prefix for focused exploration

### 2. `CONFIG_KEY_EXTRACTOR_README.md`

Comprehensive documentation covering:
- Problem statement and solution
- Usage examples and command-line options
- Understanding of `<id>` placeholders (template keys)
- Output format explanations
- Use cases and limitations
- How the tool works internally

### 3. `config_keys.json`

Generated JSON file containing:
- Complete list of all discovered keys
- Hierarchical representation
- Source file locations for each key (useful for developers)

## Key Discoveries

The utility found important configuration patterns, such as queue TLS settings:

```
queue.tls                                    # Base configuration
queue.tls.<id>.dane                         # DANE TLS policy
queue.tls.<id>.starttls                     # STARTTLS policy
queue.tls.<id>.allow-invalid-certs          # Certificate validation
queue.tls.<id>.timeout.tls                  # TLS timeout
queue.tls.<id>.timeout.mta-sts              # MTA-STS timeout
```

Where `<id>` represents a user-defined identifier like `default`, `strict`, `invalid-tls`, etc.

## Tree Layout Output

The default output format is a **hierarchical tree** showing the structure of configuration keys:

```
├── queue
│   ├── connection
│   │   └── <id>
│   │       ├── ehlo-hostname
│   │       └── timeout
│   │           ├── connect
│   │           ├── data
│   │           ├── ehlo
│   │           ├── greeting
│   │           ├── mail-from
│   │           └── rcpt-to
│   ├── route
│   │   ├── <id>
│   │   │   └── type
│   │   ├── address
│   │   ├── auth
│   │   │   ├── secret
│   │   │   └── username
│   │   └── type
│   ├── schedule
│   │   └── <id>
│   │       ├── expire
│   │       ├── max-attempts
│   │       ├── notify
│   │       ├── queue-name
│   │       └── retry
│   ├── tls
│   │   └── <id>
│   │       ├── allow-invalid-certs
│   │       ├── dane
│   │       ├── starttls
│   │       └── timeout
│   │           ├── mta-sts
│   │           └── tls
│   └── virtual
│       └── <id>
│           └── threads-per-node
```

This tree layout makes it easy to:
- **Browse** available configuration sections
- **Understand** the hierarchical relationships between keys
- **Discover** what sub-keys are available under a particular prefix
- **Identify** template patterns with `<id>` placeholders

**Remember:** This shows the *structure* and *names* of keys, not their actual values or defaults.

## Understanding `<id>` Placeholders

Keys containing `<id>` are **template keys** that support user-defined identifiers. You can create multiple instances with different names.

### Example

Instead of `queue.tls.<id>.dane`, you might define:

```toml
# In your config.toml
[queue.tls.default]
dane = "optional"
starttls = "optional"
allow-invalid-certs = false

[queue.tls.strict]
dane = "require"
starttls = "require"
allow-invalid-certs = false

[queue.tls.legacy]
dane = "disable"
starttls = "optional"
allow-invalid-certs = true
```

Then reference these policies elsewhere in your configuration:
```toml
[queue.strategy]
tls = "default"  # Or "strict", "legacy", etc.
```

## How It Works

The utility analyzes patterns in the Rust source code where the `config` object is accessed:

### Patterns Detected

1. **Simple string access:**
   ```rust
   config.property("key.path")
   config.value("server.hostname")
   ```

2. **Tuple-based access:**
   ```rust
   config.property(("queue", "tls", "dane"))
   config.value(("directory", id, "type"))
   ```

3. **Dynamic key discovery:**
   ```rust
   config.sub_keys("queue.virtual", ".threads-per-node")
   // Generates: queue.virtual.<id>.threads-per-node
   ```

4. **Multiple suffix patterns:**
   ```rust
   config.sub_keys_with_suffixes("queue.tls", &[
       ".dane",
       ".starttls",
       ".allow-invalid-certs",
       ".timeout.tls",
       ".timeout.mta-sts",
   ])
   // Generates all: queue.tls.<id>.dane, queue.tls.<id>.starttls, etc.
   ```

### Processing Steps

1. Scan all Rust files in the `crates/` directory
2. Apply regex patterns to find configuration access calls
3. Extract and normalize key names
4. Build hierarchical representation
5. Track source locations for each key
6. Export in requested format

## Usage Examples

### View All Keys in Tree Format (Default)

```bash
python3 extract_config_keys.py
```

Output: Hierarchical tree of all 173 configuration keys

### Find All Queue-Related Keys

```bash
python3 extract_config_keys.py --filter queue --format flat
```

Output:
```
queue.connection
queue.connection.<id>.ehlo-hostname
queue.connection.<id>.timeout.connect
queue.connection.<id>.timeout.data
queue.route
queue.route.<id>.type
queue.route.address
queue.tls
queue.tls.<id>.dane
queue.tls.<id>.starttls
...
```

### Export to JSON for Programmatic Use

```bash
python3 extract_config_keys.py --format json --output config_keys.json
```

Then query with `jq`:
```bash
# Count total keys
jq '.keys | length' config_keys.json

# Find where a specific key is defined in source code
jq '.contexts["queue.tls.<id>.dane"]' config_keys.json
```

### Explore Specific Configuration Sections

```bash
# Server configuration
python3 extract_config_keys.py --filter server --format tree

# JMAP settings
python3 extract_config_keys.py --filter jmap --format tree

# Storage configuration
python3 extract_config_keys.py --filter storage --format tree
```

## Command-Line Options

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

## Statistics

- **173 unique configuration keys** discovered
- **797 Rust files** analyzed
- Includes both concrete keys and template keys with `<id>` placeholders

## Output Formats

### 1. Tree Format (Default)

Hierarchical tree showing key structure:
- Easy to browse and understand relationships
- Shows nesting visually
- Best for exploration and discovery

### 2. Flat Format

Newline-separated list of full key paths:
- Easy to grep and filter
- Simple for scripting
- Best for finding specific keys

### 3. JSON Format

Structured data with:
- `keys`: Array of all keys
- `hierarchy`: Nested object representation
- `contexts`: Source file locations and access patterns

Best for:
- Programmatic processing
- Building tools and validators
- IDE integration

## Use Cases

1. **Configuration Exploration** - Discover what configuration options are available
2. **Documentation** - Generate reference documentation for configuration keys
3. **Validation** - Build config file validators that check for typos
4. **IDE Support** - Create autocomplete data for editors
5. **Migration Tools** - Identify configuration differences between versions
6. **Troubleshooting** - Verify if a configuration key actually exists

## What This Tool Does NOT Provide

While the tool discovers all configuration keys, it does NOT extract:

- ❌ Default values for keys
- ❌ Data types (string, integer, boolean, duration, etc.)
- ❌ Valid value options or ranges
- ❌ Validation rules or constraints
- ❌ Documentation or descriptions
- ❌ Whether a key is required or optional
- ❌ Relationships between keys

**What it DOES provide:**

- ✅ Complete list of all available configuration key names
- ✅ Hierarchical structure showing key relationships
- ✅ Template patterns (keys with `<id>` placeholders)
- ✅ Source file locations for each key

To find default values, data types, and validation rules, you'll need to examine the source code files identified in the JSON output's `contexts` field.

## Limitations

This tool finds keys that are **programmatically accessed** in the code. It may not find:

- Keys that are only documented but not yet implemented
- Keys that are constructed dynamically at runtime using string concatenation
- Deprecated keys that are no longer referenced in the code
- Some complex configuration patterns that use computed variables

However, it **will** find all keys that Stalwart currently uses in its configuration parsing logic.

## Example: Solving the Original Problem

**Question:** "Does `queue.outbound.tls` exist?"

**Using the tool:**

```bash
python3 extract_config_keys.py --filter queue --format flat | grep tls
```

**Result:**
```
queue.tls
queue.tls.<id>.allow-invalid-certs
queue.tls.<id>.dane
queue.tls.<id>.starttls
queue.tls.<id>.timeout.mta-sts
queue.tls.<id>.timeout.tls
```

**Answer:** The key `queue.outbound.tls` does not exist. The actual keys are `queue.tls.<id>.*` where you define named TLS policies (like `default`, `strict`, etc.) and reference them in your queue strategy configuration.

## Files Created

1. **`extract_config_keys.py`** - The main utility script
2. **`CONFIG_KEY_EXTRACTOR_README.md`** - Detailed documentation and usage guide
3. **`config_keys.json`** - Generated JSON output with all keys
4. **`extract_config_keys.md`** - This document (overview and summary)

## Getting Started

1. Navigate to your Stalwart source directory:
   ```bash
   cd /path/to/stalwart
   ```

2. Run the extractor:
   ```bash
   python3 extract_config_keys.py
   ```

3. Explore the tree output, or use `--filter` to narrow down to specific sections

4. For detailed usage information, see `CONFIG_KEY_EXTRACTOR_README.md`

## Conclusion

The Configuration Key Extractor solves the problem of discovering available configuration options in Stalwart Mail Server by providing a comprehensive, source-code-based list of all configuration keys. While it doesn't provide values or documentation for these keys, it gives you the complete structure and hierarchy, making it much easier to explore what's configurable and understand the organization of Stalwart's configuration system.

Use this tool alongside the official documentation and source code to build a complete understanding of Stalwart's configuration capabilities.
