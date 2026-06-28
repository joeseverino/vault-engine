# Security Policy

## Supported versions

`severino-vault-engine` is pre-1.0; only the latest released minor receives
fixes. Pin a version and upgrade forward.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

- Preferred: GitHub **Security Advisories** → *Report a vulnerability* on
  <https://github.com/joeseverino/vault-engine/security/advisories/new>
- Or email **github@jseverino.com** with a description, affected version, and a
  reproduction.

You'll get an acknowledgement within 72 hours. Fixes ship in a patch release;
credit is given unless you prefer otherwise.

## Supply-chain assurances

- **Trusted Publishing (OIDC).** Releases are published to PyPI directly from
  the `joeseverino/vault-engine` GitHub Actions workflow — no long-lived API
  tokens exist to leak.
- **Signed provenance (PEP 740).** Each release uploads PyPI attestations, so a
  downloaded artifact can be traced to the exact workflow run and commit.
- **Pinned actions + Dependabot.** CI actions are pinned to commit SHAs and
  kept current by Dependabot; dependency bumps are reviewed before merge.
- **Least privilege.** Workflows default to `contents: read`; `id-token: write`
  is granted only to the publish job.
