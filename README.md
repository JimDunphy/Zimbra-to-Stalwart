# Zimbra → Stalwart Migration Project

## Overview
This project is dedicated to helping administrators and developers transition from **Zimbra Collaboration Suite (FOSS Edition)** to **Stalwart Mail Server**. It will document how Stalwart operates from a Zimbra perspective, provides scripts and utilities to simplify migration, and develops a modern web interface inspired by the Zimbra Web Client but powered by **JMAP** and current web technologies.

## Motivation
Zimbra has long been a capable and feature-rich collaboration suite, but its open-source future is uncertain.  
In recent years, **Zimbra has stopped providing full FOSS patch releases**, and the build process for community editions has become increasingly fragile. For example, as of late 2025, third-party repositories required for building FOSS packages have broken, preventing reliable updates or security patches.  

More details are available in the Zimbra wiki:  
[Zimbra FOSS Source Code Only Releases – wiki.zimbra.com](https://wiki.zimbra.com/wiki/Zimbra_Foss_Source_Code_Only_Releases)

In contrast, **Stalwart Mail Server** represents a modern, sustainable model for open-source email infrastructure:
- Fully written in **Rust** for performance, safety, and maintainability.  
- Implements modern standards like **JMAP**, **IMAP**, **SMTP**, and **LMTP** natively.  
- Offers transparent **enterprise licensing** ($60/year) while still allowing complete self-compilation of the enterprise edition from source.  
- Modular, efficient, and actively maintained by a responsive developer community.  

After running Stalwart in parallel for several months, it has proven stable, efficient, and significantly easier to manage and extend than Zimbra’s Java-based architecture.  
This project exists to help others make the same transition smoothly — preserving existing data and workflows while moving to a modern, open ecosystem.

## Zimbra vs Stalwart (Comparison Overview)

| Feature / Aspect                | Zimbra (FOSS Edition)                     | Stalwart Mail Server                       |
|---------------------------------|-------------------------------------------|--------------------------------------------|
| **Language / Platform**         | Java (Jetty, Lucene, OpenLDAP)            | Rust (high performance, memory safe)       |
| **Web Protocols**               | SOAP, partial REST, proprietary endpoints  | Full JMAP + IMAP + SMTP + LMTP             |
| **Architecture**                | Monolithic services, multiple daemons     | Modular microservices, unified configuration |
| **Database / Storage**          | MySQL / MariaDB, file blobs               | Embedded key-value store (RocksDB) or external DB |
| **Build & Patch Model**         | FOSS releases no longer maintained        | Fully open-source with optional paid license |
| **Extensibility**               | SOAP/Java extensions                      | JSON/TOML configs, modular backend APIs     |
| **Webmail Client**              | Zimbra Web Client (legacy)                | Planned modern JMAP client (in this project) |
| **Security Model**              | Dependent on patches from commercial branch | Regular open-source updates, TLS-first design |
| **Ease of Deployment**          | Complex multi-package system               | Single binary or container-based deployment |
| **Community Support**           | Declining                                 | Growing, active developer community         |

## Objectives
- Document operational parallels between Zimbra and Stalwart (mail flow, LDAP, proxying, configuration layout, etc.).
- Provide migration scripts to export, convert, and import mail, accounts, and folders.
- Develop a browser-based mail client that mirrors Zimbra’s workflow and layout using modern frameworks and JMAP.

## Key Components
- **Migration Toolkit:** Scripts and utilities for exporting Zimbra mailboxes, folders, and accounts, and importing them into Stalwart via JMAP or Maildir.
- **Documentation Library:** Technical mappings between Zimbra components and Stalwart equivalents.
- **Web Interface Prototype:** A mail client replicating Zimbra’s interface using modern web frameworks.
- **Validation Tools:** Scripts and test data for verifying migration accuracy and functional parity.

## Getting Started
1. Clone this repository:
   ```bash
   git clone https://github.com/JimDunphy/Stalwart-Tools.git
   cd Stalwart-Tools

2. Review available scripts in the `scripts/` directory.
3. Consult the `docs/` section for migration procedures and configuration mappings.
4. Follow progress on the `web/` interface prototype.

## Roadmap
- [x] Repository initialization and migration script stubs  
- [ ] Configuration mapping between Zimbra and Stalwart  
- [ ] Mail export to Maildir with correct flag preservation (:2,S, :2,RS, etc.)  
- [ ] JMAP-based import and account creation utilities  
- [ ] Webmail interface prototype replicating Zimbra layout and UX  
- [ ] Dockerized test environment for validation  

## Future Directions
The long-term focus of this project is on **fully open systems**, not on extending or maintaining Zimbra.  
Since reliable FOSS builds of Zimbra are no longer sustainable, all future work will center on **Stalwart** as the foundation.

While JMAP is a modern standard and well supported by Stalwart, there are currently **limited full-featured mail user agents (MUAs)** that natively support JMAP across desktop and mobile platforms.  
To bridge this gap, we plan to apply the same concept proven in the [zpush-shim project](https://github.com/JimDunphy/zpush-shim)—where a lightweight Jetty-based shim was used to optimize ActiveSync performance—but this time, to bring **ActiveSync support directly to Stalwart**.

This approach would allow:
- Native integration with default **iOS** and **Android** mail clients.  
- Continued compatibility with **ActiveSync-capable clients** like Outlook.  
- A pathway to test, validate, and transition users without depending on Zimbra’s REST or SOAP APIs.  

Long-term goals include:
- Implementing a **JMAP-to-ActiveSync translation layer** for seamless synchronization.  
- Adding **CalDAV/CardDAV** support for calendar and contact data.  
- Building a **web-based admin console** for user and domain management.  
- Expanding migration tools for shared folders, distribution lists, and aliases.  
- Conducting performance benchmarks comparing mail throughput and sync efficiency across protocols.

## Contributing
Contributions and testing feedback are welcome. Please open an issue or pull request if you’d like to participate in development, documentation, or testing.

## License
This project is licensed under the **MIT License**.


