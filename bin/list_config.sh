#!/bin/bash
#
# Stalwart Configuration Viewer
#
# This script uses the Stalwart Management API to display configuration values
# from both the local config.toml and the database store.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
STALWART_URL="${STALWART_URL:-http://localhost:8080}"
STALWART_USER="${STALWART_USER:-admin}"
STALWART_PASS="${STALWART_PASS:-}"

# Function to print usage
usage() {
    cat << EOF
${BOLD}Stalwart Configuration Viewer${NC}

Usage: $0 [OPTIONS]

${BOLD}Options:${NC}
  -u, --url URL          Stalwart server URL (default: ${STALWART_URL})
  -a, --user USER        Admin username (default: ${STALWART_USER})
  -p, --password PASS    Admin password (or set STALWART_PASS env var)
  -l, --list [PREFIX]    List all config keys with optional prefix filter
  -g, --get KEYS         Get specific keys (comma-separated)
  -P, --prefix PREFIXES  Get all keys with prefixes (comma-separated)
  -G, --group PREFIX     Group keys by prefix (e.g., queue.tls)
  -s, --suffix SUFFIX    Suffix for grouping (used with --group)
  -j, --json             Output raw JSON (always complete, never truncated)
  -t, --tree             Display in tree format (default for --list)
  -w, --width NUM        Truncate values at NUM characters for readability (default: 0 = no truncation)
  -h, --help             Show this help message

${BOLD}Examples:${NC}
  # List all configuration keys
  $0 --list

  # List all queue configuration
  $0 --list queue

  # Get specific keys
  $0 --get storage.data,storage.blob,server.hostname

  # Get all keys with a prefix
  $0 --prefix queue.tls,queue.schedule

  # Group queue TLS configurations
  $0 --group queue.tls --suffix dane

  # Output raw JSON (always complete)
  $0 --list queue --json

  # Truncate long values for readability
  $0 --list certificate --width 80

${BOLD}Environment Variables:${NC}
  STALWART_URL     Server URL (default: http://localhost:8080)
  STALWART_USER    Admin username (default: admin)
  STALWART_PASS    Admin password

${BOLD}Authentication:${NC}
  You can provide password via:
  - Command line: -p password
  - Environment: export STALWART_PASS=password
  - Interactive prompt (if not provided)

EOF
    exit 0
}

# Function to prompt for password
prompt_password() {
    if [ -z "${STALWART_PASS}" ]; then
        echo -n "Enter admin password: " >&2
        read -s STALWART_PASS
        echo >&2
    fi
}

# Function to make API call
api_call() {
    local endpoint="$1"
    local auth="${STALWART_USER}:${STALWART_PASS}"

    local response
    local http_code

    response=$(curl -s -w "\n%{http_code}" -u "${auth}" "${STALWART_URL}${endpoint}")
    http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "200" ]; then
        echo -e "${RED}Error: HTTP ${http_code}${NC}" >&2
        echo "$body" | jq -r '.error // .message // .' 2>/dev/null || echo "$body" >&2
        exit 1
    fi

    echo "$body"
}

# Function to display list in tree format
display_tree() {
    local prefix="$1"
    local json="$2"

    echo -e "${BOLD}Configuration Keys${NC}${prefix:+ for prefix: ${CYAN}${prefix}${NC}}\n"

    # Extract items from JSON and build tree
    local keys=$(echo "$json" | jq -r '.data.items | to_entries[] | .key' 2>/dev/null)

    if [ -z "$keys" ]; then
        echo -e "${YELLOW}No configuration keys found${NC}"
        return
    fi

    local total=$(echo "$json" | jq -r '.data.total' 2>/dev/null)
    echo -e "${GREEN}Total keys: ${total}${NC}\n"

    # Simple tree display
    echo "$keys" | sort | while read -r key; do
        local value=$(echo "$json" | jq -r --arg key "$key" '.data.items[$key]' 2>/dev/null)
        local depth=$(echo "$key" | tr -cd '.' | wc -c)
        local indent=$(printf '%*s' $((depth * 2)) '')

        # Color code the key based on patterns
        local colored_key="$key"
        case "$key" in
            store.*|directory.*|server.*|certificate.*|tracer.*|storage.*)
                colored_key="${YELLOW}${key}${NC} ${CYAN}[local]${NC}"
                ;;
            queue.*|session.*|jmap.*|spam-filter.*|sieve.*)
                colored_key="${GREEN}${key}${NC} ${BLUE}[database]${NC}"
                ;;
        esac

        # Truncate long values if TRUNCATE_WIDTH > 0
        if [ "$TRUNCATE_WIDTH" -gt 0 ] && [ ${#value} -gt "$TRUNCATE_WIDTH" ]; then
            local trim_to=$((TRUNCATE_WIDTH - 3))
            value="${value:0:${trim_to}}..."
        fi

        echo -e "${indent}${colored_key} = ${value}"
    done
}

# Function to display key-value pairs
display_keys() {
    local json="$1"

    echo -e "${BOLD}Configuration Values${NC}\n"

    local keys=$(echo "$json" | jq -r '.data | keys[]' 2>/dev/null)

    if [ -z "$keys" ]; then
        echo -e "${YELLOW}No configuration keys found${NC}"
        return
    fi

    echo "$keys" | while read -r key; do
        local value=$(echo "$json" | jq -r --arg key "$key" '.data[$key]' 2>/dev/null)

        # Color code based on key pattern
        local colored_key="$key"
        case "$key" in
            store.*|directory.*|server.*|certificate.*|tracer.*|storage.*)
                colored_key="${YELLOW}${key}${NC} ${CYAN}[local]${NC}"
                ;;
            queue.*|session.*|jmap.*|spam-filter.*|sieve.*)
                colored_key="${GREEN}${key}${NC} ${BLUE}[database]${NC}"
                ;;
        esac

        echo -e "${colored_key}"
        echo -e "  ${value}\n"
    done
}

# Function to display grouped configuration
display_group() {
    local json="$1"

    echo -e "${BOLD}Grouped Configuration${NC}\n"

    local total=$(echo "$json" | jq -r '.data.total' 2>/dev/null)
    echo -e "${GREEN}Total items: ${total}${NC}\n"

    # Display each grouped item
    echo "$json" | jq -r '.data.items[] | @json' | while read -r item; do
        local id=$(echo "$item" | jq -r '._id')
        echo -e "${CYAN}${BOLD}[${id}]${NC}"

        echo "$item" | jq -r 'to_entries[] | select(.key != "_id") | "\(.key) = \(.value)"' | while read -r line; do
            echo "  $line"
        done
        echo ""
    done
}

# Parse command line arguments
ACTION=""
PREFIX=""
KEYS=""
PREFIXES=""
GROUP_PREFIX=""
GROUP_SUFFIX=""
OUTPUT_JSON=false
OUTPUT_TREE=true
TRUNCATE_WIDTH=0  # Default: no truncation (safe for data integrity)

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -u|--url)
            STALWART_URL="$2"
            shift 2
            ;;
        -a|--user)
            STALWART_USER="$2"
            shift 2
            ;;
        -p|--password)
            STALWART_PASS="$2"
            shift 2
            ;;
        -l|--list)
            ACTION="list"
            if [[ $# -gt 1 && ! "$2" =~ ^- ]]; then
                PREFIX="$2"
                shift
            fi
            shift
            ;;
        -g|--get)
            ACTION="get"
            KEYS="$2"
            shift 2
            ;;
        -P|--prefix)
            ACTION="get"
            PREFIXES="$2"
            shift 2
            ;;
        -G|--group)
            ACTION="group"
            GROUP_PREFIX="$2"
            shift 2
            ;;
        -s|--suffix)
            GROUP_SUFFIX="$2"
            shift 2
            ;;
        -j|--json)
            OUTPUT_JSON=true
            OUTPUT_TREE=false
            shift
            ;;
        -t|--tree)
            OUTPUT_TREE=true
            OUTPUT_JSON=false
            shift
            ;;
        -w|--width)
            TRUNCATE_WIDTH="$2"
            shift 2
            ;;
        -n|--no-truncate)
            TRUNCATE_WIDTH=0
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is required but not installed${NC}" >&2
    echo "Install it with: sudo apt install jq  # or brew install jq" >&2
    exit 1
fi

# Prompt for password if needed
if [ -z "$ACTION" ]; then
    echo -e "${RED}Error: No action specified${NC}" >&2
    echo "Use --help for usage information" >&2
    exit 1
fi

prompt_password

# Execute the requested action
case "$ACTION" in
    list)
        endpoint="/api/settings/list"
        if [ -n "$PREFIX" ]; then
            endpoint="${endpoint}?prefix=${PREFIX}"
        fi

        response=$(api_call "$endpoint")

        if [ "$OUTPUT_JSON" = true ]; then
            echo "$response" | jq .
        elif [ "$OUTPUT_TREE" = true ]; then
            display_tree "$PREFIX" "$response"
        else
            echo "$response" | jq -r '.data.items | to_entries[] | "\(.key) = \(.value)"'
        fi
        ;;

    get)
        params=""
        if [ -n "$KEYS" ]; then
            params="keys=${KEYS}"
        fi
        if [ -n "$PREFIXES" ]; then
            if [ -n "$params" ]; then
                params="${params}&"
            fi
            params="${params}prefixes=${PREFIXES}"
        fi

        if [ -z "$params" ]; then
            echo -e "${RED}Error: No keys or prefixes specified${NC}" >&2
            exit 1
        fi

        response=$(api_call "/api/settings/keys?${params}")

        if [ "$OUTPUT_JSON" = true ]; then
            echo "$response" | jq .
        else
            display_keys "$response"
        fi
        ;;

    group)
        if [ -z "$GROUP_PREFIX" ]; then
            echo -e "${RED}Error: No prefix specified for grouping${NC}" >&2
            exit 1
        fi

        endpoint="/api/settings/group?prefix=${GROUP_PREFIX}"
        if [ -n "$GROUP_SUFFIX" ]; then
            endpoint="${endpoint}&suffix=${GROUP_SUFFIX}"
        fi

        response=$(api_call "$endpoint")

        if [ "$OUTPUT_JSON" = true ]; then
            echo "$response" | jq .
        else
            display_group "$response"
        fi
        ;;
esac
