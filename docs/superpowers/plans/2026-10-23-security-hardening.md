# ChargeForward Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task.

**Spec:** `docs/superpowers/specs/2026-10-23-security-hardening-design.md`

**Goal:** Deliver six sequential one-commit pull requests that harden the API, ingestion transport, container runtime, and repository supply chain.

**Architecture:** Keep security controls close to the boundary they protect. API middleware owns response policy; endpoint validation owns computational bounds; the HTTP transport owns egress and payload limits; Docker owns process privilege; GitHub workflows own code and dependency scanning.

**Tech stack:** Python 3.10+, FastAPI, pandas, urllib, Docker, GitHub Actions, pytest.

---

## Task 1: API response hardening

**Files:** `chargeforward/api.py`, `tests/test_api.py`, design and plan documents.

1. Write a failing test for required response headers and disabled production docs.
2. Run the targeted test and confirm failure.
3. Add security-header middleware and environment-controlled docs URLs.
4. Run targeted and full tests.
5. Commit once, push, open PR, wait for CI, merge.

## Task 2: Input and response bounds

**Files:** `chargeforward/api.py`, `tests/test_api.py`, `README.md`.

1. Write failing tests for county validation and station pagination.
2. Run them and confirm failure.
3. Add constrained query/path types plus `limit` and `offset` response metadata.
4. Run targeted and full tests.
5. Commit once, push, open PR, wait for CI, merge.

## Task 3: Safe outbound HTTP transport

**Files:** `chargeforward/http_client.py`, `tests/test_http_client.py`, `.env.example`.

1. Write failing tests for HTTPS enforcement, host allowlisting, and response size limits.
2. Run them and confirm failure.
3. Add URL validation and bounded streaming reads with configurable maximum bytes.
4. Run targeted and full tests.
5. Commit once, push, open PR, wait for CI, merge.

## Task 4: Least-privilege containers

**Files:** `Dockerfile`, `docker-compose.yml`, `scripts/verify_container_security.py`, `.dockerignore`.

1. Add a failing static verifier for non-root user, health check, read-only filesystem, and dropped capabilities.
2. Run it and confirm failure.
3. Harden the image and compose services while retaining writable temporary filesystems.
4. Run the verifier, tests, and Docker build.
5. Commit once, push, open PR, wait for CI, merge.

## Task 5: Static application security analysis

**Files:** `.github/workflows/codeql.yml`, `README.md`.

1. Add CodeQL for Python and JavaScript on pull requests, pushes to main, and a weekly schedule.
2. Set `contents: read` and `security-events: write` explicitly.
3. Validate YAML and repository site tests.
4. Commit once, push, open PR, wait for CI and CodeQL, merge.

## Task 6: Dependency and disclosure controls

**Files:** `.github/dependabot.yml`, `.github/workflows/dependency-review.yml`, `SECURITY.md`, `README.md`.

1. Add weekly grouped updates for pip, GitHub Actions, and Docker.
2. Add dependency review for pull requests with read-only permissions.
3. Document private vulnerability reporting and supported versions.
4. Validate configuration, run the full suite, and verify the website.
5. Commit once, push, open PR, wait for all checks, merge.

## Review focus

- Headers must be present on errors as well as successful responses.
- Validation must reject malformed or oversized county values before pandas filtering.
- Download size limits must apply even when `Content-Length` is absent or dishonest.
- Containers must remain able to write only where runtime libraries need temporary space.
- Workflow permissions must be no broader than each action requires.
- Documentation must describe security boundaries accurately.
