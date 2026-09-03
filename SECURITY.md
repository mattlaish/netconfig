# Security

## Current hardening baseline

The built-in console remains stdlib-only. It now supports optional built-in TLS, failed-login throttling keyed by peer IP + normalized username, failed/successful authentication auditing, JSON security/access logs, secure-response headers, health/readiness endpoints, and Prometheus-text metrics. HSTS is emitted only when the built-in server is actually serving TLS.

The enforced CSP is intentionally transitional because the legacy UI still contains inline style attributes and inline event handlers. It enforces restrictive default/base/object/frame/form/connect boundaries while temporarily allowing inline script/style. A stricter nonce-based CSP is emitted in report-only mode so route/template extraction can remove those inline constructs without breaking the console.

## Service credential bootstrap

Preferred unattended vault unlock is systemd `LoadCredential=`. NetConfig reads `$CREDENTIALS_DIRECTORY/vault-master` automatically. A root-controlled `NETCONFIG_MASTER_FILE` is the migration/non-systemd alternative. `NETCONFIG_MASTER` remains supported only as a legacy compatibility path and should not be the production recommendation.

Never put device passwords, SNMP secrets, SMTP credentials, vault plaintext, or private keys in logs, metrics, settings JSON, command-line arguments, or repository files.

## Remediation safety

Remediation now fetches the live configuration immediately before execution, computes a semantic plan against the baseline, emits vendor negations where supported, arms an automatic rollback guard, applies the plan, re-fetches configuration, verifies semantic convergence, and only then cancels/confirms the rollback guard. Platforms without an implemented automatic rollback primitive fail closed for remediation.

Remediation is also fail-closed when the stored baseline was scrubbed. A sanitized baseline is evidence, not an executable desired-state source, and must never be pushed back to a device.

Current automatic rollback support:

- Cisco IOS / ASA / Arista EOS: timed `reload in 5`, cancelled only after verification.
- JunOS: `commit confirmed 5`, confirmed only after verification.
- Cisco NX-OS, Comware, MikroTik, Generic: remediation is blocked until a tested automatic rollback strategy exists.

Real-vendor lab validation remains required before calling these guards production-validated.

## Known security debt — session lifetime (DEFERRED)

**Explicitly deferred:** console sessions currently have no idle timeout or absolute expiry. Session tokens persist in process memory until logout or process restart. This is a known security weakness for an administrative console.

Do not silently change this behavior in the current hardening slice. A future dedicated session-lifecycle change must add, at minimum:

- idle expiration;
- absolute lifetime;
- expired-session cleanup;
- session rotation on authentication / privilege transition where applicable;
- logout/expiry audit evidence;
- tests for expiry, concurrent requests, CSRF behavior, and clock-boundary cases.

Until that work lands, deployments should treat console token theft as valid for the lifetime of the server process and rely on TLS, host access control, short administrative exposure windows, and explicit logout as compensating controls.

## Read-only API tokens

API bearer tokens are separate from console session cookies. Tokens are generated randomly, stored only as SHA-256 hashes, mapped to an existing NetConfig role, constrained by explicit read scopes, and auditable by token name. The plaintext token is returned only once at creation. The API has no configuration-write endpoints in this slice. Revoke unused tokens promptly. The server refuses bearer-token authentication over cleartext non-loopback HTTP; use built-in TLS or a loopback reverse-proxy backend.

## Syslog-triggered collection boundary

The UDP syslog receiver is disabled by default, bounded by queue size/message size, and defaults to non-privileged udp/5514. A configuration-change event triggers collection only when the UDP peer source IP exactly matches an inventory device. Deployments using relays/NAT must not assume embedded syslog host fields are trusted; trusted-relay identity validation is future work.
