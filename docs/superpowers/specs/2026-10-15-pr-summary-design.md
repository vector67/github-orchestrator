# What a PR is for: the pr-summary plugin

Date: 2026-10-15. Issue #29.

## Problem

The hardest part of a review is the first contact with a PR. Today the
orchestrator answers a review request with draft comments and some prose
appended to `agent-changes.md`, a log it shares with CI and rebase notes. It
never says what the PR was asked to do, what its author says it does, what
the code does, why the change was needed, or whether those agree.

## What it is

A Claude Code plugin, `pr-summary`, that runs in any repository with no
github-orchestrator installed. The orchestrator's Summary tab (the first
tab, before Board) reuses it with two additions, `--work-dir` and `--gh-account`
([its spec](2026-10-15-summary-tab-design.md)). Nothing in it imports
`github_orchestrator`.

You give it a PR (URL, or a number in the current repository). It prints a
summary in five sections and names the scratch folder holding the working
files.

## Sections

Shown in this order:

| Section   | Question                                       | Length          |
| --------- | ---------------------------------------------- | --------------- |
| Requested | What did the ticket ask for?                   | one sentence    |
| Claimed   | What does the author say they did?             | one or two      |
| Intent    | What do the implementation and the tests do?   | one or two each |
| Why       | Why was the change necessary?                  | two or three    |
| Alignment | Do these agree? Every mismatch, in trust order | a list          |

## Witnesses

Each section except Alignment is a **witness**: an agent with a fixed prompt
(its agent definition), a tool list the CLI enforces, and an input folder a
deterministic script prepared.

| Witness        | Reads                                                                                                                                                                            | Tools                               |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| requested      | the ticket key, then the ticket itself and nothing else                                                                                                                          | Read, Write, Glob, Atlassian (read) |
| claimed        | everything the PR's authors wrote: title, description, their comments and review replies on this PR, commit messages, comments and docstrings added in the diff, changes to docs | Read, Write, Glob                   |
| implementation | the diff of production files with comments and docstrings stripped                                                                                                               | Read, Write, Glob                   |
| tests          | the diff of test files with comments and docstrings stripped                                                                                                                     | Read, Write, Glob                   |
| why            | the ticket key, the repo's why guidance, earlier PRs' non-author comments, this PR's non-author human comments; then linked and earlier tickets and Confluence through Atlassian | Read, Write, Glob, Atlassian (read) |
| alignment      | the five witnesses' outputs only                                                                                                                                                 | Read, Write, Glob                   |

### Isolation

Each witness runs as its own process:

```
claude -p --restricted --plugin-dir <plugin> --agent pr-summary:<witness>
       --model opus --permission-mode acceptEdits --no-session-persistence
       --allowedTools <its Atlassian read tools>
```

with its input folder as the working directory. Checked by hand on
2026-10-15: under `--restricted` the file tools refuse any path outside the
working directory, the agent's `tools:` list is all it gets, and with a
working directory outside git the session gets no `git status` and no
CLAUDE.md. The prompt the process receives is a fixed string in the script,
so no model ever writes another model's instructions.

Rules:

- **The PR's authors** are the PR's author plus every login that authored or
  co-authored one of its commits.
- **Requested comes from the ticket only.** No ticket key found means the
  requested witness does not run; the section reads "No ticket found" and
  Alignment lists that first. Requested names the ticket's reporter and
  assignee, so a ticket the author wrote is visible.
- **Why never reads anything the PR's authors wrote**, on this PR or any
  earlier one, and never reads bot comments (a bot's summary of this PR is the
  code or the description again). When nothing outside the authors explains
  the change, Why says so: that is a finding, not a failure.
- **Implementation and tests never see** the title, branch, description,
  commit messages, comments, docstrings, docs or each other's inputs.
- **No witness has Bash or the network**, except Requested and Why reaching
  Jira and Confluence through the Atlassian tools, read tools only, named one
  by one. Their prompts forbid following Jira's links back to the PR or its
  commits.
- **Every witness writes `output.json`** into its working directory.
- **Atlassian unreachable, or the ticket not found**: Requested and Why say
  which in `gaps` and stop. They never guess at a ticket.

### Witness output

```json
{
  "witness": "implementation",
  "display": "One or two sentences for the section.",
  "claims": [
    {
      "id": "I1",
      "text": "Rows with no values are dropped before export.",
      "evidence": ["src/export/rows.py:40-52"]
    }
  ],
  "gaps": ["What this witness could not establish, and why."]
}
```

Claim ids are prefixed by witness: `R` requested, `C` claimed, `I`
implementation, `T` tests, `W` why. Evidence is a file and line range in the
head commit, a ticket key or field, or a URL. Stripping keeps every line in
place, so line numbers in the stripped diff are the head file's.

## Alignment

The alignment judge reads the five outputs and walks a **ladder** in trust
order: why, requested, implementation, tests, claimed. Each witness is checked
against every witness above it, and the higher witness is taken as true: a
lower witness never corrects a higher one. If the code suggests the ticket
asked for the wrong thing, that is listed as "implementation disagrees with
requested", and the reviewer decides.

Its prompt says alignment is rare. Mismatches include contradiction, scope
creep (the code does more than asked), an unrequested refactor, something
asked for that the code does not do, behaviour the tests do not pin, and a
claim nothing supports. A mismatch is not a judgement that the PR is wrong.

```json
{
  "mismatches": [
    {
      "lower": "implementation",
      "higher": "requested",
      "kind": "unrequested-refactor",
      "text": "Also renames the export service; the ticket asks only to hide the button.",
      "claims": ["I3", "R1"]
    }
  ]
}
```

`kind` is one of `contradiction`, `scope-creep`, `unrequested-refactor`,
`not-done`, `untested`, `unsupported`. Mismatches are listed rung by rung:
requested against why, then implementation against both, then tests against
the three above, then claimed against all four.

`render.py`, not the judge, decides whether everything matches: only when
every witness produced a valid output and the list is empty. A witness that
did not run or failed is shown as the first rung ("No ticket found",
"Why failed: …").

## Preparing the inputs

`scripts/summarise.py` reads the code from the **local clone** it is run in:
it finds the remote that names the PR's repository, fetches
`refs/pull/<n>/head` into it, and reads the changed files, their contents and
their history with `git`. The diff is taken against the merge base of the
base and head commits, as GitHub does. When the working directory is not a
clone of the repository, or the fetch fails, it stops with status 3, saying
why and how many API calls the remote route would take; `--use-github-api`
reads the same through the GitHub API instead, two calls per changed file,
and the skill passes it only after the user agrees. Everything else comes
from GitHub through `gh`, as whatever account `gh` is logged in as. It:

1. Reads the PR through GraphQL: title, body, author, branch, base and head
   SHAs, creation time, changed-file count, and every page of its commits
   with authors, comments, reviews and review threads, each author's login
   and whether it is a bot.
2. Reads the config (below) from the merge base, never the head, so a PR
   cannot change how it is summarised.
3. Finds the ticket key: the first match of `ticket_pattern` in the first
   source in `ticket_sources` that has one, whose project is in
   `ticket_projects` when that is set.
4. Sorts every changed file into exactly one of, in this order: ignored,
   docs, tests, production.
5. Fetches each production and test file at the base commit (under its
   previous path when renamed) and the head commit; an added or deleted file
   has one side empty. Binary files and submodules are skipped and listed in
   `skipped.txt`. Comments and docstrings are replaced by spaces with
   tree-sitter, keeping every line where it was, and the stripped versions
   are diffed; hunks whose only changes are blank lines are dropped. A file
   in a language tree-sitter cannot parse is diffed unstripped and listed in
   `unstripped.txt`. The stripped new version of each changed file goes
   beside the diff under `files/`, so a witness can read the code around a
   hunk before calling something missing.
6. Collects the comments and docstrings the diff adds, and the docs diffs,
   for Claimed.
7. Finds earlier PRs for Why: merged PRs found by searching for the ticket
   key, then the PRs behind the last commits to the three production files
   with the most changed lines, at most five in all. It leaves out this PR
   and any PR merged after this one was opened. From each it keeps the title
   and description only when an author of this PR did not write them, and
   the bodies of comments by humans who are not authors of this PR, with
   quoted lines (`>`) and suggestion blocks removed.
8. Caps each code witness's inputs at 300,000 characters: the diffs first,
   cutting the largest first, then whole files in what is left. Whatever is
   cut is named in `truncated.txt`.
9. Writes each witness's folder into a fresh randomly named temporary
   directory outside any git repository.

A login is a bot when GitHub says so, when it ends in `[bot]`, or when it is
listed in the config's `bots`.

## Running

`scripts/summarise.py <pr>` runs `prepare.py`, starts the five witnesses at
once, waits, copies their `output.json` files into the alignment folder, runs
the judge, then runs `render.py` and prints its markdown and the scratch
folder's path. A witness that fails or runs past ten minutes is recorded as
failed; the rest continue. A witness that cannot reach the tools its agent
file names writes only `{"unavailable": "<why>"}` and is run once more after
30 seconds; if it is unavailable again it fails, and the judge never sees it.
Any failed witness makes the run exit non-zero after printing the summary,
naming each failure on stderr.

`scripts/render.py` checks each `output.json` against its shape and prints
the summary in section order. A missing or malformed output shows as that
section's failure.

The skill is a thin wrapper: it runs
`uv run ${CLAUDE_PLUGIN_ROOT}/scripts/summarise.py $ARGUMENTS` in the
background and prints what it printed.

## Config

The repository's `.github/pr-summary.toml` at the base commit wins. When it is
absent, `--config <file>` names a fallback (the orchestrator will pass its
instance `config.toml`). With neither, the defaults apply. Both use a
`[pr_summary]` table; the two are never merged.

```toml
[pr_summary]
ticket_pattern = "[A-Z][A-Z0-9]+-[0-9]+"
ticket_sources = ["title", "branch"]
ticket_projects = []
tests = ["**/tests/**", "**/test/**", "**/spec/**", "**/testdata/**", "**/__tests__/**", "**/test_*.py", "**/*_test.py", "**/conftest.py", "**/*_test.go", "**/*.test.*", "**/*.spec.*"]
docs = ["**/*.md", "**/*.rst", "**/*.adoc", "**/*.ipynb", "docs/**", "**/docs/**", "**/README*", "**/CHANGELOG*", "**/CHANGES*", "**/NEWS*", "**/CONTRIBUTING*", "**/AUTHORS*", "**/changelog.d/**", "**/news/**", "**/releasenotes/**"]
ignore = ["**/*.lock", "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock"]
bots = ["codecov-commenter", "CLAassistant", "sonarcloud", "netlify", "vercel"]
why_guidance = ""
```

The values above are the defaults. `why_guidance` is free text for the Why
witness, such as where design decisions are written down; it keeps
organisation-specific knowledge out of the public prompts.

## Packaging

```
.claude-plugin/marketplace.json      lists ./plugins/pr-summary
plugins/pr-summary/
  .claude-plugin/plugin.json
  skills/pr-summary/SKILL.md         runs summarise.py
  agents/<witness>.md                six agents: fixed prompt, tools, model
  scripts/summarise.py, prepare.py, render.py
  scripts/pr_summary/                their logic
```

The scripts carry their dependencies inline for `uv run`. Others install the
plugin with `claude plugin marketplace add <owner>/github-orchestrator` and
`claude plugin install pr-summary@<marketplace>`. It needs `gh`, `uv`,
`claude` and, for Requested and Why, an Atlassian MCP server.

## Known limits

- **Some files cannot be stripped**: markup that embeds code (`.vue`,
  `.svelte`, `.html`, `.astro`), plain text, and files with no grammar
  (`Makefile`, `Dockerfile`, extensionless scripts). They reach the code
  witnesses with their comments, listed in `unstripped.txt`. Docstrings are
  recognised in Python only; Rust `#[doc]`, Elixir `@doc` and the like stay in.
- **Bots GitHub calls users** are caught only by the `-bot` and `[bot]`
  suffixes and the default `bots` list.
- **A co-author whose commit email is not linked to a GitHub account** counts
  as an author by name, but their comments, posted under a login, reach Why.
- **Code carries the author's words too**: identifiers, test names, log and
  error strings, file names and fixtures reach the implementation and tests
  witnesses. Stripping literals would cost more meaning than it saves.
- **The author may have written the ticket or Confluence pages.** The script
  cannot map a GitHub login to an Atlassian account; Requested shows the
  reporter and assignee so the reviewer can see it.
- **Jira can lead back to the PR** through its development panel and remote
  links. The prompts forbid following them; nothing enforces it.
- **Reviewers' comments on this PR** often react to the description, so Why
  sees their reading of the PR.
- **Atlassian tool names** depend on how the server was added. The agents list
  the read tools of the two common setups, `mcp__atlassian__*` and the
  claude.ai connector; another name needs the agent files edited.
- **The default ticket pattern** also matches `UTF-8` or `SHA-256`; set
  `ticket_projects` to rule them out.

## Testing

`prepare.py`, `summarise.py` and `render.py` are written test-first. Their
logic (ticket lookup, file sorting, stripping, author and bot filtering,
earlier-PR selection, truncation, folder layout, rendering) runs against
GitHub responses written into the tests, never live `gh`, and the witness
launcher against a fake `claude`. The agents' prompts are checked by running
the skill on real PRs and by adversarial review: agents hunting for any way a
witness can see what it must not.
