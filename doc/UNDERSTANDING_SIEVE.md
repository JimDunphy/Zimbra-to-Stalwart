# Understanding Sieve in Stalwart

Stalwart integrates the [IETF Sieve mail filtering language](https://www.rfc-editor.org/rfc/rfc5228) to let you inspect and act on messages as they traverse the platform. This document explains how the language works, how Stalwart wires it into both user and server workflows, and how you can deploy scripts to build features like comprehensive mail archiving.

## What Is Sieve?

- **Purpose:** A declarative, sandboxed DSL defined in RFC 5228 for filtering email messages. It focuses on “if this condition is true, take that action” logic, without loops or side effects that could hang an MTA.
- **Extensions:** Sieve has dozens of optional capabilities registered with IANA. Stalwart exposes nearly all of them, including [RFC 5804 ManageSieve](https://www.rfc-editor.org/rfc/rfc5804), [RFC 8580 JMAP for Sieve](https://www.rfc-editor.org/rfc/rfc8620), and vendor modules like `vnd.stalwart.expressions`.
- **Basic anatomy:** Scripts start with `require` to enable extensions, then define tests (`if`, `elsif`, `else`) and actions (`fileinto`, `redirect`, `keep`, `discard`, `set`, etc.). Example:

```sieve
require ["envelope", "redirect", "fileinto", "variables"];

if envelope :matches "from" "*@customer.com" {
    fileinto :copy "Archive/Customers";    # keep normal delivery plus archive
}

if header :contains "X-Internal" "outbound" {
    redirect "archive@example.org";        # BCC outbound flow
    keep;
}
```

See the language guide in the [Sieve tutorial](https://www.rfc-editor.org/rfc/rfc5228#section-2) and the [IANA extension registry](https://www.iana.org/assignments/sieve-extensions/sieve-extensions.xhtml) for the full grammar and available modules.

## Where Sieve Runs in Stalwart

Stalwart provides two interpreters that consume scripts stored either on disk (trusted) or per user (untrusted):

| Layer | Config prefix | Use case | Example assets |
| --- | --- | --- | --- |
| **Server-controlled (“trusted”)** | `sieve.trusted.*` | Scripts configured by operators and executed inside the SMTP pipeline (`stage_connect`, `stage_rcpt`, `stage_data`, …). They run with elevated privileges, can access listener metadata, and may alter delivery for every tenant. | `tests/resources/smtp/sieve/*.sieve` |
| **User-managed (“untrusted”)** | `sieve.untrusted.*` | Scripts uploaded by end users via ManageSieve or JMAP. They run in a sandbox per account, with quotas and capability limits, and can only affect that user’s mailbox. | `tests/resources/jmap/sieve/*.sieve` |

“Trusted” simply means the operator vouches for the script: it is deployed centrally, runs with access to server internals, and can impact other tenants. “Untrusted” scripts are customer-supplied and therefore constrained—Stalwart enforces per-account resource limits (`sieve.untrusted.limits.*`) and disables sensitive extensions unless explicitly enabled. Both interpreters share the same `sieve-rs` parser but execute with different policies.

## Deploying Trusted (“Server”) Scripts

1. **Write the script** and place it under a directory the server can read (e.g., `resources/sieve/archive_all.sieve`). Use the samples under `tests/resources/smtp/sieve/` as starting points. `stage_data.sieve` shows how to edit headers, redirect copies, and iterate MIME parts.
2. **Configure the interpreter** in `config.toml`:
   ```toml
   [sieve.trusted]
   default.directory = "resources/sieve"

   [sieve.trusted.scripts."stage_data"]
   file = "resources/sieve/archive_all.sieve"
   ```
   Keys live alongside other server settings (`resources/config/config.toml:36-42` configures the ManageSieve listener; similar blocks exist for trusted Sieve).
3. **Reload or restart** Stalwart so the interpreter recompiles the script.

### Example: Archiving Inbound + Outbound Mail

In the discussion you referenced, the goal is to BCC every inbound and outbound message into an archive mailbox. A trusted `stage_data` script can do that:

```sieve
require ["envelope", "redirect", "variables"];

if envelope :domain :is "to" "example.com" {
    redirect "inbound-archive@example.net";
    keep;
}

if envelope :domain :is "from" "example.com" {
    redirect "outbound-archive@example.net";
    keep;
}
```

Because trusted scripts run inside the SMTP transaction, both directions can be captured before final delivery. You can branch by recipient, sender, listener, or any metadata exposed via the `variables`/`eval` extensions (`tests/resources/smtp/sieve/stage_data.sieve` demonstrates advanced conditionals).

## Deploying User (“Untrusted”) Scripts

- **ManageSieve**: Enable the listener on port `4190` (already present in `resources/config/config.toml`). Users connect with any ManageSieve client (e.g., `managesieve` CLI, Roundcube, Stalwart’s CLI) to upload scripts, set the active one, and list capabilities. Reference RFC 5804 for the protocol details.
- **JMAP for Sieve**: Stalwart’s API and CLI (`crates/cli/src/modules/export.rs`) can query, import, and export Sieve scripts via the JMAP extension, letting you manage scripts programmatically.
- **Storage model**: User scripts are stored as objects within Stalwart’s directory/lookup stores; see `crates/types/src/collection.rs:348-444` for how the `SieveScript` collection is exposed.
- **Configuration boundary**: Per-account scripts are *not* configured in `config.toml`. That file only controls server-level (“trusted”) hooks. User logic must be uploaded via ManageSieve or JMAP, which is why the discussion you referenced instructs you to “open the archive mailbox” and paste the script through a ManageSieve-capable client.

### Common `require[]` capabilities

Each script advertises which extensions it needs. Some frequently-used ones from the discussion thread:

| Extension | Purpose | Spec |
| --- | --- | --- |
| `fileinto` | Files a message into a named mailbox. | [RFC 5228 §4.1](https://www.rfc-editor.org/rfc/rfc5228#section-4.1) |
| `mailbox` | Tests whether a mailbox exists, used with `fileinto :create`. | [RFC 5490](https://www.rfc-editor.org/rfc/rfc5490) |
| `imap4flags` | Reads/sets IMAP system/user flags (`addflag`, `removeflag`). | [RFC 5232](https://www.rfc-editor.org/rfc/rfc5232) |
| `fileinto :copy` | Deliver copies while preserving `keep`. | [RFC 3894](https://www.rfc-editor.org/rfc/rfc3894) |
| `variables` | Stores temporary strings for later substitution. | [RFC 5229](https://www.rfc-editor.org/rfc/rfc5229) |
| `envelope` | Tests SMTP envelope sender/recipient. | [RFC 5228 §4.2](https://www.rfc-editor.org/rfc/rfc5228#section-4.2) |
| `redirect` | Sends the message to another address (used for archiving). | [RFC 5228 §4.2](https://www.rfc-editor.org/rfc/rfc5228#section-4.2) |

The archive mailbox snippet from the forum (`require ["fileinto","mailbox","imap4flags"]; ...`) therefore says, “I need to be able to file messages, create folders, and adjust seen flags,” which only works when the script is installed as that user’s active ManageSieve script.

## How Many Hooks and Scripts Can I Attach?

### Trusted SMTP stages

Stalwart wires one script entry per SMTP stage, comparable to where you might drop milter callbacks. The core stages live under the `[session.*]` config blocks (see `tests/src/smtp/inbound/scripts.rs:47-118`):

| Stage block | When it runs | Typical uses | Example script binding |
| --- | --- | --- | --- |
| `[session.connect]` | Immediately after TCP connect, before greeting. | IP reputation, geo checks, tarpits. | `[session.connect]\nscript = "'dropBadIps'"` |
| `[session.ehlo]` | After EHLO/HELO. | Blocklisted hostnames, per-domain throttles, HELO sanity checks. | `[session.ehlo]\nscript = "'script_two'"` |
| `[session.mail]` | On MAIL FROM. | Sender rewriting, SPF/DMARC derived policy, blocklists. | `[session.mail]\nscript = "'rejectBadFrom'"` |
| `[session.rcpt]` | On each RCPT TO. | Recipient validation, aliases, per-user rules. | `[session.rcpt]\nscript = "'rcptPolicy'"` |
| `[session.data]` | After the full message body arrives but before queuing. | Archiving, header/body rewriting, virus policies. | `[session.data]\nscript = "'mailArchive'"` |

Scripts referenced in those blocks must exist under `sieve.trusted.scripts.*`. You can define them inline or via file macros:

```toml
[sieve.trusted.scripts."script_one"]
contents = '''
require ["variables", "extlists", "reject"];
if string :list "${env.helo_domain}" "list/blocked-domains" {
    reject "551 5.1.1 Your domain '${env.helo_domain}' has been blocklisted.";
}
'''

[sieve.trusted.scripts."script_two"]
contents = "%{file:/opt/stalwart-smtp/etc/sieve/my-script.sieve}%"

[session.ehlo]
script = "'script_two'"
```

In this example `script_one` is embedded inline, while `script_two` loads its contents from disk using the `%{file:...}%` macro described in the [trusted interpreter docs](https://stalw.art/docs/sieve/interpreter/trusted) that ship with 0.14.1. Once declared, pointing `[session.ehlo].script` at `'script_two'` ensures every EHLO executes the code in `/opt/stalwart-smtp/etc/sieve/my-script.sieve`.

Each `script = "name"` simply looks up a compiled program from `sieve.trusted.scripts.<name>`. You can define as many named scripts as you like; the stage just picks one by name. If you need to compose multiple policies at the same stage, use the standard Sieve [`include` extension](https://www.rfc-editor.org/rfc/rfc6609) or the `vnd.stalwart.expressions` `eval` helper to fan out to other files—Stalwart doesn’t limit how many includes you chain, apart from the configurable `sieve.trusted.limits.nested-includes` (`tests/src/smtp/inbound/scripts.rs:65-72`). This mirrors “multiple milters per stage” by letting you keep small, focused scripts and include them from a dispatcher.

### User layer

ManageSieve/JMAP accounts can store multiple scripts simultaneously (list, upload, delete), but only one is “active” at a time per RFC 5804 semantics. Stalwart follows that spec, so users can keep draft scripts, switch between them, or share snippets with `include`s, yet only the active one executes on delivery.

### Beyond SMTP stages

- **Spam filter or other internal features** can also rely on trusted Sieve scripts by pointing to the same `sieve.trusted.scripts.<name>` entries—`tests/src/smtp/inbound/scripts.rs:118-166` shows how every file under `tests/resources/smtp/sieve/` is loaded automatically.
- **Configurable headers**: `[session.data.add-headers]` (see `tests/src/smtp/inbound/scripts.rs:96-105`) toggles which automatic headers are added before the `stage_data` script runs, giving your script predictable inputs like `Received-SPF` or `Auth-Results`.

Net result: you can hook Sieve anywhere the SMTP state machine exposes a `session.*.script` key, keep an arbitrary number of script definitions, and modularize them with the standard `include` mechanism so they behave much like stacking multiple milters.

## Real-World Example: `mailArchive` Script

The GitHub discussion you linked proposes journaling every inbound and outbound message. Here’s a production-ready `mailArchive` trusted script plus the config needed to deploy it.

### Script (`resources/sieve/mail_archive.sieve`)

```sieve
require ["envelope", "redirect", "variables"];

/* Archive all inbound mail */
if envelope :domain :is "to" "example.com" {
    redirect "archive-inbound@example.net";
    keep;  # continue with normal delivery
}

/* Archive all outbound mail */
if envelope :domain :is "from" "example.com" {
    redirect "archive-outbound@example.net";
    keep;
}

/* Optional: journal specific VIPs elsewhere */
if envelope :localpart :is "to" "ceo" {
    redirect "vip-archive@example.net";
    keep;
}
```

### Configuration

```toml
[sieve.trusted]
default.directory = "resources/sieve"

[sieve.trusted.scripts."mailArchive"]
file = "resources/sieve/mail_archive.sieve"

[session.data]
script = "'mailArchive'"
```

Steps:

1. Place the `.sieve` file in `resources/sieve/` (or any directory referenced by `default.directory`).
2. Register the script under `sieve.trusted.scripts."mailArchive"` pointing to the file path (or inline `contents`).
3. Assign the SMTP `DATA` hook to run that script by setting `[session.data].script`.
4. Reload/restart Stalwart so the interpreter compiles the new script.

Result: every message passing through `stage_data` triggers `mailArchive`, which BCCs copies to your archival mailboxes while preserving the original delivery. You can further modularize by including other policy files from within `mailArchive` if the logic grows large.

### Real-World Example: RCPT Envelope Normalization

Forwarding MXes sometimes send dual-delivery copies using alternate domains, causing later filters to compare `RCPT TO <user@relay.example.com>` with headers listing `user@example.com`. Normalize during the RCPT stage so downstream checks see consistent recipients:

```sieve
require ["envelope", "variables"];

# Rewrite *@relay9.example.com to the canonical domain
if envelope :matches "to" "*@relay9.example.com" {
    set "localpart" "${1}";
    set_envelope "to" "${localpart}@example.com";
    # Optional for debugging:
    # addheader "X-Envelope-Rewritten" "relay9.example.com -> example.com";
}
```

Attach it to the RCPT hook:

```toml
[sieve.trusted.scripts."rcptNormalize"]
contents = "%{file:/opt/stalwart/etc/sieve/rcpt_normalize.sieve}%"

[session.rcpt]
script = "'rcptNormalize'"
```

Now every RCPT command runs `rcptNormalize` before the spam filter, preventing false `FORGED_RECIPIENTS` hits when upstream aliases rewrite the envelope.

## Deployment Checklist for Beginners

### 1. Preparing trusted scripts

1. Create a directory for operator-managed scripts (e.g., `mkdir -p resources/sieve`).
2. Write your `.sieve` file in that directory.
3. Add a `[sieve.trusted.scripts."<name>"]` block in `config.toml` pointing to the file or inline `contents`.
4. Point the relevant `[session.*].script` option to that name.
5. Run `cargo fmt --all` (if you changed config templates) and reload Stalwart:
   ```bash
   # systemd example
   sudo systemctl reload stalwart
   # or restart if reload is not available
   sudo systemctl restart stalwart
   ```

### 2. Testing trusted scripts safely

- Use the sample configs in `tests/src/smtp/inbound/scripts.rs` as references.
- Run `cargo test -p tests --features smtp` (or the full `cargo test --workspace --all-features`) to ensure scripts compile.
- Tail logs (`journalctl -u stalwart -f`) during reloads; syntax errors are logged with file names and line numbers.

### 3. Managing user scripts (ManageSieve)

1. Ensure the listener in `resources/config/config.toml` has `[server.listener."sieve"]` enabled (defaults to port `4190`).
2. Use a ManageSieve client. Example with [sieveshell](https://www.cyrusimap.org/sieve/managesieve/commands.html):
   ```bash
   sieveshell -u alice -a alice mail.example.com
   # inside the shell
   list
   put ~/Downloads/vacation.sieve vacation
   activate vacation
   logout
   ```
3. To script deployments, leverage the Stalwart CLI (see `crates/cli/src/modules/export.rs`) or any JMAP client that supports the Sieve capability.

**Python helper:** `sieve_upload.py` now understands multiple actions:

- Import / update (default action):
  ```bash
  python3 sieve_upload.py --import \
    --host mail.example.com \
    --username archive@example.com \
    --password 'SuperSecret' \
    --script-file resources/sieve/mail_archive.sieve \
    --script-name mailArchive
  ```
  Add `--dry-run` to preview the upload without connecting, or `--no-activate` to leave the script inactive.
- List scripts on the server:
  ```bash
  python3 sieve_upload.py --list --host mail.example.com --username archive@example.com --password 'SuperSecret'
  ```
  Active scripts are marked with `*`.
- Delete a script (does not touch the active flag unless you delete the active script):
  ```bash
  python3 sieve_upload.py --delete mailArchive --host mail.example.com --username archive@example.com --password 'SuperSecret'
  ```

The helper uses implicit TLS by default; add `--starttls` for STARTTLS or `--plaintext` for lab-only testing.

### 4. Verifying end-to-end

- Send test emails that match each branch of your script.
- Inspect delivery logs or archived mailboxes to confirm redirects/fileinto actions happened.
- For user scripts, use IMAP/POP to verify filing, and ManageSieve `list/activate` to confirm the right script is active.

Following these steps lets even first-time admins build, deploy, and validate Sieve filters with confidence.

### 5. Where do these paths live?

- **Relative paths in this guide** (such as `resources/sieve`) refer to the Stalwart repository or the directory you deploy under `STALWART_PATH`. In packaged installs that typically resolves to `/opt/stalwart/share` for assets and `/opt/stalwart/data` for persisted data, but you can set `STALWART_PATH` to any location.
- **Config macros** like `%{env:STALWART_PATH}%` (see `resources/config/config.toml:53`) expand to whatever base path you configure. If you follow the sample config, scripts stored under `resources/sieve` in the repo end up in `/opt/stalwart/share/resources/sieve` after installation.
- **Data vs. config:** Scripts you expect to edit manually belong in your configuration directory (often `/etc/stalwart` or `/opt/stalwart/etc`). The `[sieve.trusted.scripts."name"]` `file =` setting can point anywhere the daemon has read access, so adjust it if your environment uses a different layout.

### 6. “Sieve editor” in community discussions

The community post you referenced mentions “heading over to the sieve script editor” inside the archive mailbox. Stalwart itself does **not** ship a web UI; that phrase assumes you are using an external client that can edit user-level Sieve scripts:

- **Webmail (Roundcube, Snappymail, etc.)**: many have ManageSieve plugins that expose a GUI editor tied to the server’s `4190` ManageSieve endpoint. Opening the archive mailbox there simply means logging in as the archive user and pasting the script through that plugin.
- **Desktop clients**: Thunderbird offers the “Sieve Message Filters” add-on that provides a similar editor; create a session pointing at `mail.example.com:4190`, authenticate as the archive mailbox, and upload the code snippet.
- **CLI / custom tooling**: you can run `sieveshell`, the Stalwart CLI, or your own script that uses either ManageSieve or JMAP Sieve to upload the snippet to the archive account.

So the “editor” is not a built-in Stalwart page—it's any ManageSieve-capable tool you prefer. The script they provided (`fileinto :create "${header.X-fileTo}"`) must be installed as that mailbox’s active user script (see the steps above) so that when the archive account receives redirected copies, it files them into the folders indicated by the `X-FileTo` header.

## Helpful References

- RFC 5228 – Sieve: [https://www.rfc-editor.org/rfc/rfc5228](https://www.rfc-editor.org/rfc/rfc5228)
- IANA Sieve extension registry: [https://www.iana.org/assignments/sieve-extensions/sieve-extensions.xhtml](https://www.iana.org/assignments/sieve-extensions/sieve-extensions.xhtml)
- RFC 5804 – ManageSieve protocol: [https://www.rfc-editor.org/rfc/rfc5804](https://www.rfc-editor.org/rfc/rfc5804)
- RFC 8620 / JMAP for Sieve: [https://www.rfc-editor.org/rfc/rfc8620](https://www.rfc-editor.org/rfc/rfc8620)
- Stalwart docs on SMTP filtering with Sieve: [https://stalw.art/docs/category/sieve-scripting](https://stalw.art/docs/category/sieve-scripting)

Armed with these resources and the sample scripts in the repo, you can customize Stalwart’s mail flow—from per-user rules to global archiving policies—using the same, well-understood Sieve language.
