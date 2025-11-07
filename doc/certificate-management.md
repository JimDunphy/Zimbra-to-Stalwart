# Stalwart Certificate Management

## Overview

Stalwart provides comprehensive certificate management capabilities through its HTTP API and CLI tools. This document covers certificate reloading, ACME support, and programmatic certificate management.

## Certificate Reloading

### API Endpoint
- **Endpoint**: `GET /api/reload/certificate`
- **Purpose**: Reloads TLS certificates without server restart
- **Authentication**: Requires admin privileges with `SettingsReload` permission

### CLI Command
```bash
stalwart-cli -c admin:yourpassword -u http://127.0.0.1 server reload-certificates
```

### Direct API Call
```bash
curl -X GET \
  -H "Authorization: Basic $(echo -n 'admin:yourpassword' | base64)" \
  -H "Content-Type: application/json" \
  "http://127.0.0.1/api/reload/certificate"
```

### Use Case
Perfect for automated certificate renewal scripts (e.g., Let's Encrypt) to update certificates without service interruption.

## ACME (Automatic Certificate Management Environment)

Stalwart provides built-in ACME support for automatic certificate provisioning and renewal:

### Supported Challenge Types
- `TLS-ALPN-01`
- `DNS-01` 
- `HTTP-01`

### Supported DNS Providers
- Cloudflare
- DigitalOcean
- OVH
- DeSEC
- Custom DNS providers

### Configuration Keys
- `acme.*`
- `acme.<id>.directory` - ACME directory URL (e.g., Let's Encrypt endpoints)
- `acme.<id>.contact` - Contact email addresses
- `acme.<id>.domains` - Domains to cover
- `acme.<id>.challenge` - Challenge type to use
- `acme.<id>.provider` - DNS provider
- `acme.<id>.secret` - API credentials
- `acme.<id>.renew-before` - Renewal timing

## Other Certificate-Related APIs

### Configuration Management
- `GET /api/settings/list?prefix=certificate` - List all certificate configurations
- `POST /api/settings` - Update certificate configurations using UpdateSettings structure
- `DELETE /api/settings/{prefix}` - Delete certificate configurations

### UpdateSettings Structure
```json
[
  {
    "type": "insert|delete|clear",
    "prefix": "certificate.my-cert",
    "values": [
      ["cert", "-----BEGIN CERTIFICATE-----..."],
      ["key", "-----BEGIN PRIVATE KEY-----..."]
    ],
    "keys": ["certificate.my-cert.cert", "certificate.my-cert.key"]
  }
]
```

### S/MIME Certificate Management
- `/api/account/crypto` - Manage user S/MIME certificates for email encryption at rest

## Best Practices for Certificate Renewal

### 1. Use the reload endpoint instead of restarting the service
```bash
# GOOD - Zero downtime
stalwart-cli -c admin:yourpassword -u http://127.0.0.1 server reload-certificates

# AVOID - Service interruption
systemctl restart stalwart
```

### 2. Use dedicated API credentials
For automation scripts, consider creating an API user with only `SettingsReload` permission instead of using your main admin account for security.

### 3. Verify certificate reload success
Both the CLI command and API call return a JSON response with the updated configuration data.

## Configuration Storage

Certificate configurations are stored in the database (or configuration store) using keys with the pattern `certificate.*` and are loaded into memory at runtime.

## Implementation Details

The certificate reloading mechanism works as follows:
1. Stalwart server receives API call to `/api/reload/certificate`
2. Server reads updated certificate configuration from storage
3. Parses certificate data 
4. Updates in-memory certificate cache
5. Makes new certificates available immediately without restart

This approach ensures zero downtime and immediate certificate availability.

## Key Rust Implementation Files

For developers wanting to understand the implementation in detail, here are the key Rust source files:

### CLI Implementation
- `crates/cli/src/main.rs` - Main CLI entry point
- `crates/cli/src/modules/cli.rs` - Command definitions including `ServerCommands::ReloadCertificates`
- `crates/cli/src/modules/database.rs` - Implementation of server commands, including the reload-certificates handler

### HTTP API Implementation
- `crates/http/src/management/reload.rs` - HTTP handler for `/api/reload/certificate` endpoint
- `crates/http/src/management/mod.rs` - Main management API routing
- `crates/http/src/management/settings.rs` - Configuration management endpoints

### Certificate Loading and Parsing
- `crates/common/src/manager/reload.rs` - Core `reload_certificates()` function implementation
- `crates/common/src/config/server/tls.rs` - Certificate parsing logic with `parse_certificates()` function
- `crates/common/src/listener/tls.rs` - TLS listener implementation

### ACME Support
- `crates/common/src/listener/acme/mod.rs` - ACME provider management
- `crates/common/src/listener/acme/directory.rs` - ACME directory and challenge handling
- `crates/common/src/listener/acme/resolver.rs` - ACME certificate resolver
- `crates/services/src/housekeeper/mod.rs` - ACME certificate renewal scheduling

### Configuration Management
- `crates/common/src/config/inner.rs` - Configuration loading and parsing
- `crates/common/src/listener/listen.rs` - TLS connection handling

## Additional Certificate-Related API Endpoints

### Configuration Management
- `GET /api/settings/list?prefix=certificate` - List all certificate configurations
- `GET /api/settings/keys?prefixes=certificate` - Get specific certificate configuration keys
- `POST /api/settings` - Update certificate configurations (requires admin privileges)
- `DELETE /api/settings/certificate.{id}` - Delete certificate configurations

### S/MIME Management
- `GET /api/account/crypto` - Retrieve S/MIME encryption settings for current account
- `POST /api/account/crypto` - Update S/MIME encryption settings

### Certificate Information and Troubleshooting
- `GET /api/troubleshoot/tls` - TLS connection troubleshooting information
- `GET /api/dns/certificate` - Certificate-related DNS information

### Server Management
- `GET /api/reload` - Reload entire configuration (including certificates)
- `GET /api/healthz/ready` - Server readiness check
- `GET /api/healthz/live` - Server liveness check

### Permission Requirements
All certificate-related API endpoints require appropriate permissions:
- `SettingsReload` for certificate reloading
- `SettingsList` for listing configurations
- `SettingsUpdate` for updating configurations
- `SettingsDelete` for deleting configurations
- `ManageEncryption` for S/MIME operations