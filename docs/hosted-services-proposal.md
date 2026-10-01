# `hosted_services`: disclosure before import (proposal to Anthropic)

Status: PROPOSED as a standard field. This index already uses it; this note is the version we
would like to see in the Claude Code plugin marketplace manifest and in the Claude Science
import screen.

## The problem

A skill folder can contain scripts that contact outside services, require credentials, or send
the user's data somewhere. Today an importer learns that by reading the code. The Claude Science
import screen shows name and description; nothing in the marketplace manifest schema carries a
machine-readable statement of what a skill contacts.

The original forum request (feature #4): "show on the import screen which outside services a
skill contacts and which credentials it expects." This field is the smallest change that makes
that screen possible.

## The field

Per plugin (and optionally per skill), one array of disclosure records:

```json
"hosted_services": [
  {"host": "api.typesafe.ai",
   "skills": ["szl-typesafe-ai"],
   "when": "optional; only when the user supplies a key",
   "sends": "the state object the user passes",
   "credential": "TYPESAFE_API_KEY (user-owned)",
   "purpose": "second-reader evidence classification"},
  {"host": "huggingface.co",
   "skills": ["szl-science-workbench"],
   "when": "only on the explicit fetch-triage command",
   "sends": "nothing; downloads four pinned public files",
   "credential": "none",
   "purpose": "fetch a frozen public study"}
]
```

An empty array is a positive statement: this plugin contacts nothing. Absence of the field means
undisclosed, which the import screen should show as such.

## Check rule (what this index enforces today)

Every literal URL host and API hostname found in any vendored byte of the plugin must appear in a
`hosted_services` record, or the static check fails. Dynamic destinations (a host assembled at
runtime) cannot be found statically and are reported as a residual risk, not as compliance.
Credential names mentioned in SKILL.md (`*_API_KEY`, `*_TOKEN`) must appear in a `credential`
field.

## What the import screen could show

```
szl-science-skills  ·  18 skills  ·  Apache-2.0  ·  pinned f9ec7691
Contacts: huggingface.co (only on fetch-triage; downloads 4 public files; no credential)
Credentials expected: none
Index check: static PASS at 2026-10-01  ·  Verified tier: not yet
```

Three lines a researcher can read before clicking Import.

## What this does not solve

- Undeclared or dynamic destinations; a static check cannot prove their absence.
- Whether the declared purpose is honest; the field is a publisher statement.
- Name clashes, update notices and the share button from the original request; those need
  product changes, not a manifest field.

## Ask

1. Add `hosted_services` (or an equivalent name) to the marketplace manifest schema as optional.
2. Render it on the Claude Science import preview when present, and render "undisclosed" when
   absent.
3. Treat an empty array as a disclosure, not as missing data.

Reference implementation: `tools/check.py` in this repository (host extraction and matching),
`registry.json` for the current records, `CATALOG.md` for the rendered column.
