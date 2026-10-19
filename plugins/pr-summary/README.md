# pr-summary

A Claude Code plugin that tells a reviewer what a pull request is for before
they open the diff:

1. **Requested**: what the ticket asked for, from the ticket alone.
2. **Claimed**: what the authors say they did, from their words alone.
3. **Intent**: what the production code does and what the tests pin, each read
   from code with its comments and docstrings removed. Implementation also
   gets the repository's unchanged production code at the head, comments
   included, when run from a clone.
4. **Why**: why the change was needed, from tickets, Confluence, earlier pull
   requests and other people's comments, never from the authors.
5. **Alignment**: every mismatch between them, checked in trust order: why,
   requested, implementation, tests, claimed. Each mismatch is then handed to
   a critic that tries to falsify it from the witnesses' outputs and the
   code, and a final judge that decides whether the critic succeeded. The
   mismatches that stand come first; the falsified ones follow, crossed out,
   each with the critic's reason.

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

Run it from a clone of the pull request's repository: it fetches the pull
request into that clone and reads the code with `git`. Anywhere else it stops
and asks; `--use-github-api` reads the files over the GitHub API instead, at
two calls per changed file.

```
/pr-summary https://github.com/acme/shop/pull/7
```

or from a shell:

```bash
uv run --script <plugin>/scripts/summarise.py https://github.com/acme/shop/pull/7
```

`--prepare-only` writes the witnesses' input folders and stops, which is the
way to see exactly what each witness was given.

`--gh-account <login>` runs every `gh` call as that logged-in account rather
than the one `gh` has active. The plugin asks `gh auth token --user <login>`
once and hands the token to its own `gh` calls only, as `GH_TOKEN`; it never
prints it. If that lookup fails, the run stops with a message naming the
account.

`--mcp-config <file>` has every witness load only the MCP servers in that file
(`claude --mcp-config` with `--strict-mcp-config`). Without it a witness gets
whatever servers claude finds, and claude.ai connectors can still be
connecting when a witness starts, so the Jira witnesses report their tools
unavailable. Name each server in the file as `claude mcp list` does, so its
login carries over.

## Working files

Each run writes its witness folders into a fresh temporary folder, or into
`--work-dir <path>` when given. The plugin creates `<path>` if it is missing
and refuses one that is not empty, so a leftover `output.json` can never pass
for a finished witness. The last line of the output names the folder:
`Working files: <path>`.

```
<path>/
  requested/        only when a ticket key was found
  claimed/
  implementation/
  tests/
  why/
  alignment/
  critic-<n>/       one per mismatch, with the evidence and the code
  verdict-<n>/      the same, plus the critic's output as critic.json
  <witness>.log     each witness's own stdout and stderr
```

Each witness folder holds that witness's inputs, and `output.json` once the
witness finishes. `alignment` runs last, after the others have finished or
failed. A witness that cannot reach its tools (an MCP server still
connecting, say) is run once more after 30 seconds. If any witness still
fails, the run prints the summary and then exits non-zero, naming each failure.

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
tests = ["**/tests/**", "**/test/**", "**/spec/**", "**/testdata/**", "**/__tests__/**", "**/test_*.py", "**/*_test.py", "**/conftest.py", "**/*_test.go", "**/*.test.*", "**/*.spec.*"]
docs = ["**/*.md", "**/*.rst", "**/*.adoc", "**/*.ipynb", "docs/**", "**/docs/**", "**/README*", "**/CHANGELOG*", "**/CHANGES*", "**/NEWS*", "**/CONTRIBUTING*", "**/AUTHORS*", "**/changelog.d/**", "**/news/**", "**/releasenotes/**"]
ignore = ["**/*.lock", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock"]
bots = ["codecov-commenter", "CLAassistant", "sonarcloud", "netlify", "vercel"]  # logins to treat as bots besides GitHub's own
why_guidance = ""                      # where your organisation writes down its reasons
```

A file is sorted into the first of ignored, docs, tests and production whose
patterns match it.
