# Security policy

Kestrel watches AI agents that can run commands on your machine, so we take security reports
seriously.

## Supported versions

Kestrel is pre-1.0. Security fixes go into the latest release only.

## Reporting a vulnerability

**Please do not open a public issue.** Report privately through
[GitHub security advisories](../../security/advisories/new). Include what you found, how to
reproduce it, and the impact you expect. We aim to acknowledge reports within 3 days and to ship
a fix or mitigation within 30 days for confirmed issues, and we will credit you in the advisory
unless you prefer otherwise.

## What Kestrel defends against

- **Other websites in your browser.** The server listens on 127.0.0.1, rejects requests whose
  `Host` header is not local (DNS rebinding), requires a custom header and same-origin `Origin`
  for buttons, requires a bearer token for `POST /v1/events`, and serves a strict
  Content-Security-Policy.
- **Secrets in agent output.** API keys, tokens, private keys, passwords in URLs and secret-like
  assignments are scrubbed before events are stored. This is a safety net, not a guarantee.
- **Agents in the optional runner** going beyond their task: the guard hook blocks pushes to
  anything but task branches, writes outside the team folder, secret files, outbound HTTP and
  deploy or publish commands, and enforces the token budget. It fails closed.

## What it does not defend against

- **The guard is not a sandbox.** A determined or compromised agent with shell access can get
  around pattern-based rules. Run agents in a container or VM for real isolation, and review
  their changes before merging.
- **Other local users and processes** with access to your home folder can read the event store
  and the ingest token.
- **Exposing the dashboard** beyond localhost (`--host 0.0.0.0` without a firewall or an
  authenticating proxy) makes your agents' activity visible to anyone who can reach the port.

## Privacy

Kestrel sends no telemetry and makes no third-party requests. Your data stays in your home
folder (`~/.kestrel` by default).
