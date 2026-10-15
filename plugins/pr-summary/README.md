# pr-summary

A Claude Code plugin that tells a reviewer what a pull request is for before
they open the diff:

1. **Requested**: what the ticket asked for, from the ticket alone.
2. **Claimed**: what the authors say they did, from their words alone.
3. **Intent**: what the production code does and what the tests pin, each read
   from code with its comments and docstrings removed.
4. **Why**: why the change was needed, from tickets, Confluence, earlier pull
   requests and other people's comments, never from the authors.
5. **Alignment**: every mismatch between them, checked in trust order: why,
   requested, implementation, tests, claimed.

Each section is written by its own `claude -p --restricted` process whose
working directory holds only that witness's inputs, so no witness can read
another's sources. The design is in
`docs/superpowers/specs/2026-10-15-pr-summary-design.md`.

## Install

```bash
claude plugin marketplace add vector67/github-orchestrator
claude plugin install pr-summary@github-orchestrator
```

It needs `gh` (logged in with access to the repository), `uv`, `claude`, and
for Requested and Why an Atlassian MCP server.

## Use

```
/pr-summary https://github.com/acme/shop/pull/7
```

or from a shell:

```bash
uv run --script <plugin>/scripts/summarise.py https://github.com/acme/shop/pull/7
```

`--prepare-only` writes the witnesses' input folders and stops, which is the
way to see exactly what each witness was given.

## Config

Put a `[pr_summary]` table in `.github/pr-summary.toml` on the repository's
default branch. It is read from the pull request's base commit, so a pull
request cannot change how it is summarised. `--config <file>` names a fallback
for repositories without one. The defaults:

```toml
[pr_summary]
ticket_pattern = "[A-Z][A-Z0-9]+-[0-9]+"
ticket_sources = ["title", "branch"]   # where to look for the ticket key, in order
ticket_projects = []                   # e.g. ["SHOP"]; empty accepts any project
tests = ["tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*.test.*", "**/*.spec.*", "**/__tests__/**"]
docs = ["**/*.md", "**/*.rst", "**/*.adoc", "**/*.ipynb", "docs/**", "**/docs/**", "**/README*", "**/CHANGELOG*"]
ignore = ["**/*.lock", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock"]
bots = []                              # logins to treat as bots besides GitHub's own
why_guidance = ""                      # where your organisation writes down its reasons
```

A file is sorted into the first of ignored, docs, tests and production whose
patterns match it.
