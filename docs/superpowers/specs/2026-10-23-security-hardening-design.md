# ChargeForward Security Hardening Design

## Intent

Add visible, production-relevant security controls to ChargeForward while preserving its public, read-only analytics experience. The work should strengthen the API, outbound ingestion, container runtime, and software supply chain, and it should produce a clean GitHub history suitable for technical review.

## Goals

- Ship at least six independently reviewable security improvements.
- Use exactly one commit per pull request and merge each pull request before starting the next.
- Add automated evidence for every control through tests or workflow validation.
- Keep the public website and existing analytics behavior working.
- Document what each control protects and where its boundary ends.

## Non-goals

- Add authentication to public read-only endpoints.
- Claim compliance with a formal security framework.
- Add a web application firewall or paid security service.
- Hide source freshness or model methodology that is intentionally public.

## Constraints

- GitHub Pages cannot emit custom HTTP response headers, so browser policy controls must use supported HTML metadata where applicable.
- The API reads local analytical artifacts and has no write endpoints.
- Live ingestion calls a small fixed set of public HTTPS hosts.
- Existing dependencies and Python 3.10+ support must remain intact.

## Approaches considered

### Single large hardening pull request

This would minimize CI runs, but it would mix runtime, API, and supply-chain controls and make individual changes harder to review or revert.

### Six sequential one-commit pull requests — selected

Each control is isolated, verified, merged, and then becomes the base for the next change. This matches the requested history and makes each security decision auditable.

### Configuration-only security pass

Adding scanners and update bots would improve visibility, but it would leave runtime risks such as unbounded responses and root containers unchanged.

## Delivery sequence

1. Add API security response headers and disable production documentation by default.
2. Validate county input and paginate station responses to bound API work and payload size.
3. Restrict public-data HTTP downloads to HTTPS, approved hosts, and a maximum response size.
4. Run container services as an unprivileged user with read-only runtime defaults.
5. Add CodeQL static application security analysis with least-privilege workflow permissions.
6. Add dependency vulnerability review, Dependabot updates, and a documented security reporting policy.

## Security boundaries

- Headers reduce browser attack surface but do not replace TLS termination or an edge proxy.
- Pagination limits one response; deployment-level rate limits remain the responsibility of the hosting platform or reverse proxy.
- The outbound allowlist covers the official Socrata and AFDC adapters. New sources must be added intentionally.
- Container hardening limits process privileges. Host, Docker daemon, and orchestration security remain external controls.
- CodeQL and dependency review find classes of issues; they do not prove the absence of vulnerabilities.

## Acceptance criteria

- Six merged pull requests, each containing exactly one commit from its head branch.
- Existing and new tests pass after every pull request.
- Docker image builds and its configured runtime user is non-root.
- GitHub security workflows use explicit minimal permissions.
- README links to the security policy and describes the new controls without overstating them.
