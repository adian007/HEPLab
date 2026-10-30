---
title: Architecture
description: How the ASP.NET Core guide, local Python services, data path, analysis, and simulation engines are separated.
---

The public guide is an ASP.NET Core Razor Pages app. It renders Markdown pages and search data but does not call the local simulator API or read run artifacts. The simulator and data workflows run through the local Python application.

![Architecture graph: project visitors read the ASP.NET Core guide and linked engineering handbook. Local users work through the desktop workbench or CLI, which connect to Python services for data and cache, analysis artifacts, and simulation engines.](/architecture.svg)

*The hosted guide and local simulator are separate applications with separate responsibilities.*

## Public site

Razor Pages and Markdig render Markdown from `web/HEPLab.Web/Content/Docs/`. The app serves a small search index from those pages. It has no login, upload route, simulator execution, or dependency on the local project API.

## Local application

The Python service owns request validation, dataset access, job lifecycle, analysis, and artifact storage. The Rust core supplies selected numerical operations through its CLI and Python binding. PYTHIA8 and DELPHES are optional external runtimes with a pinned Linux/WSL installation.

The desktop shell packages a separate workbench frontend and supervises a local worker. It does not embed this guide. See the [desktop packaging notes](https://github.com/adian007/HEPLab/blob/main/docs/web/04-desktop-packaging.md).

## Canonical contracts

The [engineering handbook](https://github.com/adian007/HEPLab/tree/main/docs/engineering), JSON schemas, dataset manifests, and recorded reference payloads are authoritative. This site summarizes them and links to the source; it does not define an alternate physics contract.
