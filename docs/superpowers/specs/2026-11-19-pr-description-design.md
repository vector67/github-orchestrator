# Pull request description on the board: design

Issue #446.

## Why

The board shows a pull request's title but never its description, so
checking or fixing what the description says means leaving for GitHub. An
agent often writes that description, marking it with a leading 🤖, and
nothing on the way to Mark ready asks whether anyone read it.

This change shows the description on the Summary tab, lets you edit the
title and description there, and adds a check to the Mark ready dialog for a
description Claude wrote.

## Requirements

These were settled before the build. They are fixed.

1. The PR body is already fetched each poll (`github/_pull_requests.py`,
   `PullRequestState.body`), but the board API's `PullRequest` model
   (`board_api/_contract.py`) drops it. Expose it.
2. The Summary tab (`frontend/app/components/summary-tab.gts`) gets a block
   with the title and the rendered description, and Edit and Hide buttons.
   Hide folds the description to a Show description button across from the
   title. The whole tab scrolls under the title and its facts, so the
   summary's strip slides up over the description and stays under them; once
   it covers the description, Show description appears, and scrolls back to
   the top.
3. Edit opens a markdown box with Write and Preview tabs, plus a title field.
   Save PATCHes title and body together (the endpoint `assign_reviewers`
   already PATCHes in `_pull_requests.py`). Cancel throws the edit away.
4. If the body changed on GitHub since the editor opened, the save is refused:
   the body is read just before the PATCH and compared with the body the
   editor started from. The user's text is kept, both versions are shown, and
   the user chooses to save over GitHub's version or to start again from it.
5. On a pull request that has a pr-summary, a saved description shows a line
   above the report saying the report was written before the description
   changed. The summary never reruns on its own. A pull request without a
   summary shows nothing.
6. Mark ready dialog (`frontend/app/components/ready-confirm.gts`): when the
   description's first character is 🤖, an outstanding item group
   "Description written by Claude" is added, listed first.
7. That item clears when the user does any of these: presses the group's
   button in the dialog (it shows the rendered description and leaves the 🤖
   alone), saves an edit from the board's editor, or clicks into the editor's
   description field. None of them changes the 🤖.
8. The board stores that check per pull request. It expires, and the item
   returns, only when the body changes from somewhere other than the board's
   own editor: GitHub, a teammate, an agent, or the board's own
   reviewer-assignment rewrite of the body.
9. A description that does not start with 🤖 never gets the item.

## Design

### Where the body comes from

The watcher's snapshot (`change_detection/_rules.py`) keeps `body` beside
`title`; `Facts.body` carries it, and the conversation module's `PrFacts`
carries it with `polled_at` to the board, which serves both on
`GET /pull-request`.

### Saving

`PullRequests.edit_description(pr, title, body, started_from)` in the github
module reads the body, and when it differs from `started_from` writes nothing
and answers `DescriptionMoved` with the body GitHub holds. Otherwise it PATCHes
`title` and `body` together. A `gh` failure answers its sentence.

The board reaches it through a `Descriptions` port and serves
`POST /pull-request/description:save` (`title`, `body`, `started_from`). It
answers `DescriptionSave`: `saved`, `on_github` (the body GitHub holds after
the call: the saved one, or the one that moved under the edit), and the
`pull_request` as the board now serves it. A `gh` failure is `502 github-rejected`.

The watcher only sees the save on its next poll. Until a poll newer than the
save arrives, `GET /pull-request` serves the saved title and body, so the page
never flips back to the old text.

### The check

The board keeps, on the pull request's shelf (`description` / `checked`), a
digest of the body as it was checked, and the last save's title, body and
time. `PullRequest.description_checked` is true when the served body's digest
matches. That makes requirement 8 fall out: any change from anywhere else
changes the body, so the digest no longer matches.

`POST /pull-request/description:check` (`body`, the body the page showed)
records that body's digest. A save records the saved body's digest.
`PullRequest.description_saved_at` is when the board's editor last saved.

### The page

- `summary-tab.gts`: the header becomes the description block: title,
  facts, rendered description, and Edit. Editing swaps the title for a field
  and the description for a Write / Preview box; Save and Cancel. A refused
  save keeps the text and shows GitHub's version beside it, with "Save over
  GitHub's" and "Start again from GitHub's". Focusing the description field
  checks a 🤖 description.
- The summary report shows "Written before the description changed" above the
  markdown when the summary finished before `description_saved_at`.
- `summaries.ts`'s `outstandingOf` adds the `description` group first when the
  body starts with 🤖 and is not checked. `ready-confirm.gts` gives it a
  button, "Show the description", that shows the rendered description in the
  dialog and checks it. The group names the agent from the dashboard's
  `system.agent.name` ("Description written by Claude" where Claude runs the
  agents), since the front end never names an agent of its own.
- On the wall, opening Mark ready also reads the pull request, so the dialog
  knows the description.

## Seams under test

- The github contract (`tests/github/test_contract.py`), fake and `gh` alike.
- The board API over HTTP (`tests/board_api/`).
- The board in the browser (`frontend/tests/acceptance/`), against the fake
  board.
