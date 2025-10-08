# Stalwart

## Source

- <https://github.com/stalwartlabs/stalwart>

## Build

Install Rust programming language and cargo via the rustup tool.

- <https://stalw.art/docs/development/compile/>
- <https://stalw.art/docs/category/development/>

<!-- -->

    % curl --proto '==https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    % dnf install llvm-toolset
    % git clone https://github.com/stalwartlabs/stalwart.git
    % cd stalwart

Check out specific version

    % git tag --sort==-version:refname | head -1   # lists latest tag, e.g. v0.13.3
    % git checkout tags/v0.13.3

Build with Cargo and Features

    % cargo build --release -p stalwart --no-default-features --features "rocks elastic redis enterprise"

If you want the command line tool

    % cargo build --release -p stalwart-cli

## Roadmap

- <https://stalw.art/blog/roadmap/>
