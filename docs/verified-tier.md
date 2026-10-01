# Verified tier (proposal, v0.1)

Status: PROPOSED. Nothing in this document is implemented yet. The current index checks are the
static checks listed in [README](../README.md); this document specifies what an additional,
clearly labelled tier would require and what it would and would not mean.

## Why a tier

The index today tells an importer that a skill is well-formed, pinned to an immutable commit,
license-consistent, and honest about the hosts it names. It does not tell the importer whether
the skill's own code runs, whether its bundled fixtures still produce the outputs its SKILL.md
describes, or who checked. Those are different questions, and conflating them is how "checked"
becomes "trusted" without anyone deciding that.

A Verified entry answers exactly four additional questions, each with an artifact:

| Question | Artifact | Produced by |
|---|---|---|
| Does the skill's declared self-test run offline on a clean machine? | `verification/<plugin>/<sha>/selftest.json` with exit codes and captured stdout digests | index CI, no network after fetch |
| Are the vendored bytes exactly the bytes that were checked? | `verification/<plugin>/<sha>/manifest.json`: path, size, SHA-256 for every file in the plugin folder, plus a root digest | index CI |
| Did the fixture outputs match what SKILL.md claims? | `verification/<plugin>/<sha>/fixtures.json`: command, exit code, output digest, and the SKILL.md sentence it supports | index CI |
| Who ran the check, on what, when? | `verification/<plugin>/<sha>/receipt.json`: runner identity, index commit, checker version, UTC time, digest of the three files above; signed when a signing key is configured, otherwise `"signature": "UNSIGNED"` | index CI |

## What a publisher declares

A plugin opts in by adding to its registry entry:

```json
"verification": {
  "selftest": ["python -B tools/selfcheck.py", "python -B -m unittest discover -s tests"],
  "fixtures": [
    {"command": "python scripts/run.py assets/example.json", "cwd": "skills/szl-evidence-gate",
     "expect_exit": 0, "claim": "returns status ABSTAIN with counts PASS 2, FAIL 1, ABSTAIN 1"}
  ],
  "network": "none"
}
```

Commands run in a container with no network after the pinned archive is fetched, a 10-minute
budget, 2 GB memory, and the plugin folder as the only writable path. A command that tries to
reach the network fails the tier (`network: "none"` is the only value accepted in v0.1).

## What VERIFIED means

- The declared self-tests exited 0 on the index runner at the pinned commit.
- Every declared fixture command exited as declared and produced output whose digest is recorded.
- The vendored bytes match the manifest.
- The receipt names the runner and the checker version and is reproducible by re-running the
  same commands at the same commit.

## What VERIFIED does not mean

- That the skill is scientifically correct, or that its outputs are true.
- That the skill is safe to run on your data: static scans find patterns, not intent.
- That the maintainer is who they say they are; the index does not verify publisher identity.
- That the skill will trigger well in Claude; triggering quality is a separate, measured property.
- That anything was reviewed by a human. VERIFIED is machine evidence. A separate `REVIEWED`
  state, if ever added, must carry a named reviewer and a date.

## States

`LISTED` (static checks only, today's default) -> `VERIFIED` (the four artifacts exist for the
pinned commit) -> `STALE` (the pinned commit is no longer the publisher's latest tag; artifacts
remain valid for the pinned commit) -> `BLOCKED` (a check regressed or a security prerequisite
failed). Transitions are recorded, never rewritten. A new tag starts at LISTED again.

## Proposed catalog rendering

The catalog gains one column, `Tier`, with `LISTED` or `VERIFIED <receipt digest[:12]>`, and the
README import block states: "Verified means the self-test ran and the bytes match; read the skill
before relying on it."

## Open questions

1. Whether to require the publisher's own repository CI to be green at the pinned commit (easy
   to check through the commit status API, but it couples the tier to a third party's CI config).
2. Whether receipts should be signed with an index key (requires key custody) or left UNSIGNED
   with reproducibility as the guarantee. v0.1 proposes UNSIGNED, honestly labelled.
3. Whether to allow `network: "declared"` with an allowlist of hosts matching `hosted_services`;
   deferred until the disclosure field is standardized (see hosted-services-proposal.md).
