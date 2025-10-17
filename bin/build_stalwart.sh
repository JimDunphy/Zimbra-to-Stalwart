#!/usr/bin/env bash

#
# Author: Jim Dunphy 9/17/2025
# Note: 
#    internal: wiki article called: Stalwart
#

set -euo pipefail

REPO_URL="https://github.com/stalwartlabs/stalwart.git"
REPO_DIR="stalwart"
RECOMMENDED_FEATURES="rocks elastic redis enterprise"
SCRIPT_VERSION="0.1.0"

print_help() {
    cat <<'EOF'
Usage: build_stalwart.sh [OPTIONS]

Provisioning helpers tuned for Oracle Linux 9 / RHEL 9 hosts.

Options:
  --help            Show this help message with the recommended build steps.
  --version         Show script version information.
  --clone           Clone the Stalwart repository.
  --build           Build the Stalwart server using the recommended features.
  --build-cli       Build the optional Stalwart CLI tool.
  --build-all       Install prerequisites, clone the repository, checkout the latest tag, and build everything.
  --tag <name>      Checkout and build a specific git tag (default: latest tag when --build-all).

Steps performed by --build-all:
  1. Install Rust via rustup (https://stalw.art/docs/development/compile/).
  2. Install llvm-toolset using dnf (requires sudo privileges).
  3. Clone https://github.com/stalwartlabs/stalwart.git.
  4. Checkout the latest published tag (or the tag provided with --tag).
  5. Build Stalwart with "rocks elastic redis enterprise" features.
  6. Build the optional CLI tool (stalwart-cli).

Examples:
  ./build_stalwart.sh --clone
  ./build_stalwart.sh --build --tag v0.13.4
  ./build_stalwart.sh --build-all
EOF
}

print_version() {
    echo "build_stalwart.sh version ${SCRIPT_VERSION}"
}

error() {
    echo "Error: $*" >&2
    exit 1
}

info() {
    echo "[build-stalwart] $*"
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        error "Required command '$1' is not available."
    fi
}

source_cargo_env() {
    local cargo_env="$HOME/.cargo/env"
    if [ -f "$cargo_env" ]; then
        # shellcheck disable=SC1090
        source "$cargo_env"
    fi
}

install_rust_toolchain() {
    if command -v rustup >/dev/null 2>&1; then
        info "rustup already installed."
        return
    fi

    require_command curl
    info "Installing rustup (Rust toolchain manager)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source_cargo_env
    if ! command -v cargo >/dev/null 2>&1; then
        error "Cargo not found after rustup installation. Check the rustup output."
    fi
}

install_llvm_toolset() {
    if command -v llvm-ar >/dev/null 2>&1; then
        info "llvm-toolset already installed."
        return
    fi

    if ! command -v dnf >/dev/null 2>&1; then
        info "dnf not available. Please install llvm-toolset manually."
        return
    fi

    local install_cmd=(dnf install -y llvm-toolset)
    if command -v sudo >/dev/null 2>&1; then
        install_cmd=(sudo "${install_cmd[@]}")
    fi

    info "Installing llvm-toolset via dnf..."
    "${install_cmd[@]}"
}

clone_repository() {
    require_command git

    if [ -d "$REPO_DIR/.git" ]; then
        info "Repository already cloned. Fetching updates..."
        git -C "$REPO_DIR" fetch --tags --prune
    else
        info "Cloning repository $REPO_URL..."
        git clone "$REPO_URL" "$REPO_DIR"
    fi
}

checkout_ref() {
    local desired_ref="$1"

    if [ ! -d "$REPO_DIR/.git" ]; then
        error "Repository directory '$REPO_DIR' not found. Run --clone first."
    fi

    pushd "$REPO_DIR" >/dev/null
    git fetch --tags --quiet

    local ref_to_checkout=""
    if [ -n "$desired_ref" ]; then
        if git rev-parse --verify --quiet "$desired_ref" >/dev/null; then
            ref_to_checkout="$desired_ref"
        elif git rev-parse --verify --quiet "tags/$desired_ref" >/dev/null; then
            ref_to_checkout="tags/$desired_ref"
        else
            popd >/dev/null
            error "Tag or reference '$desired_ref' not found."
        fi
    else
        ref_to_checkout=$(git tag --sort=-version:refname | head -n1)
        if [ -n "$ref_to_checkout" ]; then
            ref_to_checkout="tags/$ref_to_checkout"
        else
            info "No tags found. Staying on current branch."
            popd >/dev/null
            return
        fi
    fi

    info "Checking out $ref_to_checkout..."
    git checkout "$ref_to_checkout"
    popd >/dev/null
}

build_server() {
    require_command cargo

    if [ ! -d "$REPO_DIR" ]; then
        error "Repository directory '$REPO_DIR' not found. Run --clone first."
    fi

    pushd "$REPO_DIR" >/dev/null
    source_cargo_env
    info "Building Stalwart server with recommended features..."
    cargo build --release -p stalwart --no-default-features --features "$RECOMMENDED_FEATURES"
    popd >/dev/null
}

build_cli() {
    require_command cargo

    if [ ! -d "$REPO_DIR" ]; then
        error "Repository directory '$REPO_DIR' not found. Run --clone first."
    fi

    pushd "$REPO_DIR" >/dev/null
    source_cargo_env
    info "Building Stalwart CLI..."
    cargo build --release -p stalwart-cli
    popd >/dev/null
}

main() {
    if [ $# -eq 0 ]; then
        print_help
        exit 0
    fi

    local do_clone=false
    local do_build=false
    local do_build_cli=false
    local do_build_all=false
    local checkout_tag=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --help)
                print_help
                exit 0
                ;;
            --version)
                print_version
                exit 0
                ;;
            --clone)
                do_clone=true
                ;;
            --build)
                do_build=true
                ;;
            --build-cli)
                do_build_cli=true
                ;;
            --build-all)
                do_build_all=true
                ;;
            --tag)
                shift || error "Missing value for --tag"
                checkout_tag="$1"
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
        shift || break
    done

    if $do_build_all; then
        do_clone=true
        do_build=true
        do_build_cli=true
    fi

    if ! $do_clone && ! $do_build && ! $do_build_cli && ! $do_build_all; then
        print_help
        exit 0
    fi

    if $do_build_all; then
        install_rust_toolchain
        install_llvm_toolset
    fi

    if $do_clone; then
        clone_repository
        if [ -n "$checkout_tag" ]; then
            checkout_ref "$checkout_tag"
        elif $do_build_all; then
            checkout_ref ""
        fi
    fi

    if $do_build && [ -n "$checkout_tag" ] && ! $do_clone; then
        checkout_ref "$checkout_tag"
    fi

    if $do_build; then
        build_server
    fi

    if $do_build_cli; then
        build_cli
    fi
}

main "$@"
