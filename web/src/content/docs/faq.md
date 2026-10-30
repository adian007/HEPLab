---
title: Frequently asked questions
description: Answers about the public site, local simulator, data handling, supported runtimes, and validation.
---

## Does this website run a simulation?

No. It is a static documentation site. Install and run HEPLab locally to use the simulator and analysis tools.

## Is HEPLab a full CMS detector simulation?

No. The reference bench is intentionally scoped, and the PYTHIA8/DELPHES path is a pinned fast-simulation reference. Full detector calibration and independent physics validation remain open.

## Does it upload my data?

The website does not accept uploads. The local application reads configured sources and stores cache chunks and artifacts locally. Remote CERN Open Data fetches require network access.

## What systems can run PYTHIA8 + DELPHES?

The current pinned environment is checked on Linux x86-64 and through WSL on Windows. The project does not supply native Windows or macOS simulation binaries. The Python reference bench is portable.

## Is there a desktop installer?

The Windows desktop shell has been smoke-tested, but there is no public installer at this time.

## Where are the scientific requirements?

In the [engineering handbook](https://github.com/adian007/HEPLab/tree/main/docs/engineering). Site pages summarize and link to those source records.
