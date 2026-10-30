# Local interface dependencies

The web UI runs without a font or component CDN. Compiled files are copied
unmodified from these pinned npm package archives, with the upstream licenses:

| Package | Version | Source | License |
|---|---|---|---|
| Bootstrap | 5.3.8 | [Package archive](https://registry.npmjs.org/bootstrap/-/bootstrap-5.3.8.tgz), [official documentation](https://getbootstrap.com/docs/5.3/) | MIT, included under `bootstrap/5.3.8/LICENSE` |
| IBM Plex Sans | 1.1.0 | [Package archive](https://registry.npmjs.org/@ibm/plex-sans/-/plex-sans-1.1.0.tgz), [upstream](https://github.com/IBM/plex) | SIL OFL 1.1, included under `fonts/IBM-Plex-sans-LICENSE.txt` |
| IBM Plex Mono | 1.1.0 | [Package archive](https://registry.npmjs.org/@ibm/plex-mono/-/plex-mono-1.1.0.tgz), [upstream](https://github.com/IBM/plex) | SIL OFL 1.1, included under `fonts/IBM-Plex-mono-LICENSE.txt` |

`ui-assets.json` records SHA-256 hashes computed from the actual copied files.
The runtime verification script checks them. Updating a dependency requires
replacing its files, license, version reference, and hash records together.
No npm installation is required to build or run the .NET application.
