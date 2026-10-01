# AI for Science skills

A community index of Claude skills for scientific work. Every skill is pinned to an exact commit and checked automatically before it is merged.

## Import everything with one line

Claude Science: **Skills > Import from GitHub**, paste:

    ai4science-skills/skills@v0.3.0

Claude Code:

    /plugin marketplace add ai4science-skills/skills

Then pick what you want. See [CATALOG.md](CATALOG.md) for every skill, its maintainer, license, pinned source, and any external service it contacts.

Imported skills do not update automatically. Re-import when a new tag is announced.

## What is in the index

Three plugins from two publishers, twenty-three skills, every one pinned to an immutable commit:

- **szl-science-skills** (18): a resumable research workbench and claim ledger, dataset leakage audit, model evaluation with complete denominators, numerical and theorem-to-code math checks, kernel comparison, paired qualification, reproducibility capsules, artifact lineage, unit invariants, negative-control audit, analysis-plan audit, an evidence gate (does each claim have a file behind it), a cross-implementation check (does the R rewrite match the Python original), mutation coverage for a pipeline's QC, typed compute-energy receipts, verifiable session receipts with a Methods paragraph, and a one-page reviewer pack. All Python standard library, offline, credential-free. Normal use contacts nothing; one explicit workbench command fetches four pinned public study files from Hugging Face.
- **szl-evidence-skills** (2): governed decisions that carry their own evidence, and TypeSafe Jev as an optional fail-closed second reader (requires the user's own key; optional).
- **k-dense-scientific-rigor** (3, MIT, maintained upstream by K-Dense): `experimental-design`, `statistical-power` and `scientific-critical-thinking` from [K-Dense scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) at tag v2.71.0. Selected because they are the advisory half of what the SZL checks verify: design before data, a priori power, structured appraisal. No bundled script contacts the network; the hosts listed in the catalog are citation links. The upstream repository is about 470 MB, so this entry uses the importer's selective fetch (below).

These skills check science rather than do science. They complement library-oriented collections such as [K-Dense scientific skills](https://github.com/K-Dense-AI/claude-scientific-skills): those tell an agent how to run scanpy or RDKit; these tell you whether the result that came out can be trusted as far as it claims.

To import just the source pack: `szl-holdings/szl-skills@v0.3.1`. Setup and pilot instructions are in that repository. Agent efficacy in Claude Science is not yet measured; local checks do not establish it.

## Import only the skills (feature request #1, implemented here)

A registry entry may declare `"fetch": "selected"`. The importer then lists the pinned commit's
Git tree, fetches only the license files and the requested skill folders blob by blob through the
GitHub API, verifies every blob against its Git SHA-1, and rebuilds an archive shaped like the full
one so the same validation applies. A 470 MB repository costs a few hundred kilobytes. Unauthenticated
GitHub API calls are limited to 60 per hour; CI sets `GITHUB_TOKEN`.

## Proposals

- [Verified tier](docs/verified-tier.md): an opt-in tier above today's static checks, with four reproducible artifacts (offline self-test run, byte manifest, fixture outputs, check receipt) and an explicit list of what VERIFIED does not mean. Proposed, not implemented.
- [`hosted_services` disclosure field](docs/hosted-services-proposal.md): the machine-readable statement of what a skill contacts and which credentials it expects, as this index already enforces, proposed for the marketplace manifest and the Claude Science import screen.

## What every skill must pass

| Check | Why |
|---|---|
| Plugin folder under 1 MB; only skill folders and license files are copied | Large repos fail to import |
| Unique plugin names and unique skill names | Avoids "name already in use" |
| Pinned to a full 40-character commit | A skill can't change after you import it |
| SKILL.md has a name, a description, and says what it does NOT do | Claude uses it at the right time |
| Every file the SKILL.md references exists | No skills calling code that was never committed |
| License file present and consistent with registry and SKILL.md | Clear reuse terms |
| Recognizable credential and personal-path patterns are scanned in all vendored bytes | Values are withheld from diagnostics; a static scan cannot prove that no sensitive data exists |
| Literal URL hosts and API hostnames are matched to exact declarations | Dynamic destinations still require manual review |

Passing the checks means a skill is well-formed and honest about what it touches. It does not mean the index maintainers vouch for its scientific correctness. Read a skill before relying on it.

The importer validates registry paths before making a request, reconciles each named ref with its immutable commit, refuses redirects and archive links, and limits downloads, decompression, member counts, and selected bytes. It prepares and statically checks the entire generation before replacing existing output, with rollback for handled replacement errors. It never executes skill code. See [SECURITY.md](SECURITY.md) for the remaining limits.

## Add your skill

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: add one entry to `registry.json`, run `python tools/sync.py` and `python tools/check.py`, open a pull request.

## Maintainers

Started by betterwithage on the Anthropic AI for Science forum. Co-maintainers welcome: ask on the forum or open an issue. Any skill that passes the checks and is relevant to scientific work is merged.
