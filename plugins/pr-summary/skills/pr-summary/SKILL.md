---
name: pr-summary
description: Use when about to review a pull request, or asked what a PR is for, what it was asked to do, whether it does what its ticket and author say, or to summarise a PR by intent. Takes a PR URL or number.
argument-hint: <pr-url-or-number> [--config <toml>]
---

# PR summary

Summarises a pull request in five sections: what the ticket requested, what
the authors claim, what the implementation and tests do, why the change was
needed, and every mismatch between them in trust order.

Each section comes from a separate witness that sees only its own sources, so
none of them anchors on another's. Your part is to run the script and pass
its output on untouched. Do not read the pull request, the witnesses' folders
or their outputs yourself, and do not add your own analysis unless asked:
anything you add has seen everything, which is what the witnesses are built
to avoid.

## Run it

Run this with the Bash tool in the background, from a clone of the pull
request's repository. It reads the code from that clone and fetches the pull
request into it. It takes several minutes:

```bash
uv run --script ${CLAUDE_PLUGIN_ROOT}/scripts/summarise.py $ARGUMENTS
```

When it finishes, show its output to the user exactly as printed.

If it exits with status 3, it could not read the repository locally and says
why and how many GitHub API calls reading it remotely would take. Show the
user that message and ask whether to go ahead. Only when they agree, run the
same command again with `--use-github-api` added. Never add the flag without
asking.

## When it fails

- `gh` must be logged in with access to the repository. If the repository
  needs an account other than the active one, set `GH_TOKEN` for the command.
- Requested and Why need an Atlassian MCP server. Without one, those sections
  say so and the rest still print.
- The last line names the working folder. Each witness's log is beside its
  folder as `<witness>.log`; read them only to diagnose a failure.

## Config

The repository's `.github/pr-summary.toml` on the base branch sets ticket
patterns, which files count as tests, docs or ignored, bot logins, and free
text telling the Why witness where decisions are written down. `--config <file>` names a fallback for repositories without one. See the plugin's
README for the keys.
