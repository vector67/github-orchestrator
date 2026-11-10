---
name: create-pr
description: Use when opening a pull request from a branch, including one split out of another PR — writes a detailed body with a reviewer guide, follows the repository's pull request template, links where the work came from, and opens it as a draft
---

# Create a PR

Open a pull request from a branch that is already committed. The PR is done when `gh pr create` has printed its URL and you have reported that URL.

## Inputs

Take these from whoever invoked you; read the rest from the repository.

- **Branch**: the branch to open the PR from. Default: the current branch.
- **Base**: the branch to merge into. Default: the repository's default branch (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`, or `git symbolic-ref refs/remotes/origin/HEAD` without network).
- **Origin**, when the work came from somewhere: the original PR's link, the review thread's link, and why the work moved.
- **Ticket**, when there is one: its key and link.
- **Ready**: open as ready for review only when the caller asks for it. Every other PR opens as a draft.

## Steps

1. **Read the change.** Run `git log --oneline <base>..<branch>` and `git diff --stat <base>...<branch>`, then read the diff itself. Every file in the diff is accounted for before you write: you know what it does and why it changed.

2. **Find the template.** Look for a pull request template in this order: `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/PULL_REQUEST_TEMPLATE/` (pick the file that fits the change), `docs/pull_request_template.md`, `pull_request_template.md`. Take the first one found.

3. **Write the title.** A short imperative line naming what the PR does. When the repository's recent PR titles share a convention (a ticket key in front, a type prefix), follow it; `git log --oneline -20 <base>` and `gh pr list --state merged --limit 10 --json title` show it.

4. **Write the body** to a file outside the repository, such as one from `mktemp`, so nothing new lands in the working tree.

   - **With a template**, keep its headings in its order and fill every one. A heading that does not apply gets one line saying why. Checkboxes stay checkboxes: tick only what you did. Comments in the template (`<!-- ... -->`) are instructions to you; follow them and leave them out of the body. Put the origin, the ticket and the reviewer guide under the template's closest headings, and add a heading of your own for any of them the template has no place for.
   - **Without a template**, use these headings: `## Summary`, `## Origin`, `## Reviewer guide`, `## Testing`.

   Whichever shape, the body carries:

   - **Summary**: what the change does and why, in two to four sentences.
   - **Origin**: the original PR's link, the review thread's link, and one line on why the work left that PR. Name the ticket by key with its link. When the base is not the default branch, say the PR is stacked on `<base>` and merges after it.
   - **Reviewer guide**: the files in the order to read them, one line each on what to look at, and what was moved unchanged as against what is new or edited, so the reviewer spends their attention on the new code.
   - **Testing**: the commands run and what they showed, or what is untested and why.

   Write only what the diff and the inputs support. A link or a key you were not given stays out.

5. **Open it.** Push the branch when the remote lacks it (`git push -u origin <branch>`), then:

   ```bash
   gh pr create --draft --base <base> --head <branch> --title "<title>" --body-file <body file>
   ```

   Drop `--draft` only when the caller asked for a ready PR.

6. **Report** the URL `gh pr create` printed, with the title and the base.
