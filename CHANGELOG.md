# Changelog

## v0.1.0 — 2026-11-24

### Features
- **plugin:** SentryPlugin with org, token and url options
- **tools:** read-only sentry_release_issues and sentry_latest_errors
- **access:** Sentry organization and team access provider

### Bug Fixes
- **access:** compare owners and accounts case-insensitively in guard

### Docs
- **readme:** access, tools, options, token scopes, install and develop

### Tests
- drop the FakeSentry docstring
- **live:** read-only checks against a real Sentry, skipped without AP_SENTRY_LIVE=1

### Chores
- replace the template with the apx-sentry package metadata
