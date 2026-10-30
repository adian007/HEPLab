---
title: Local API reference
description: A short orientation to the local workbench API and where its contracts are defined.
---

The HEPLab API is served by the local Python application. The guide does not expose, proxy, or call these endpoints.

Common local endpoints include:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/session` | Local session token and available engine/runtime capabilities. |
| `GET /api/v1/detector` | Detector geometry and declared dimensions. |
| `GET /api/v1/datasets` | Registered dataset manifests. |
| `POST /api/v1/jobs` | Submit a validated local run configuration. |
| `GET /api/v1/jobs/{id}` | Read the local job state and result summary. |
| `POST /api/v1/jobs/{id}/cancel` | Request cancellation of a local job. |

Mutating local requests require the session token and bounded validated inputs. The endpoint names are an orientation aid; the server and schemas remain authoritative. See the [interfaces chapter](https://github.com/adian007/HEPLab/blob/main/docs/engineering/12-interfaces.md) for request and response contracts.
