---
name: release
description: Use for "release", "cut a release" or "ship a version" of this repository — reviews everything since the last release, fixes what blocks it, runs the pre-release workflow, drafts the notes, and tags vX.Y.Z once the user says go
---

# Release

Releasing takes two workflows. `.github/workflows/pre-release.yml`, run by hand
on a commit, does the checking:

- the version is above the last release and not tagged yet;
- the CI suite, and a Python and OS matrix;
- a fresh install's smoke test;
- an upgrade from the last release, with `install.sh` and with `update`;
- loading the board in headless Chrome.

`.github/workflows/release.yml` runs when a `vX.Y.Z` tag is pushed. It refuses a
commit with no passing pre-release run, and publishes the wheel that run tested,
with the annotated tag's message as the notes. Then it installs the release
fresh, and updates to it from the release before.

`LAST` below is the last published release,
`gh release view --json tagName -q .tagName`, and the range is `LAST..main`.

01. Start from a pushed, green `main`. Push anything unpushed with `push-properly`
    first, then check that the newest CI run on `main` passed with
    `gh run list --workflow CI --branch main --limit 1`.

02. Propose the version. Read `git log --oneline LAST..main`. While the major
    version is 0, bump the minor version when users see a new feature or a config
    change, and the patch version when the range only fixes things. Write down the
    proposal and the commits that decided it, for step 8.

03. Review the range in this order, keeping each finding with its file and the
    commit that introduced it:

    1. The leak script, the same way `push-properly` runs it:
       `uv run python .claude/skills/push-properly/leak_check.py LAST..main`,
       judged the same way.
    2. `git diff --stat LAST..main`, read for deletions nobody meant, generated
       files, large binaries and files outside `src/`, `tests/`, `frontend/`,
       `docs/`, `plugins/`, `.github/` and `.claude/skills/`.
    3. Docs drift: read `README.md` and `docs/how-to-use.md` against what the
       range changed. A command, option, config key or screen they describe that
       now works differently is a finding.
    4. `/code-review` with `LAST` as the fixed point, Standards axis only, over the
       whole diff. A release has no single spec.
    5. `/blast-radius` aimed at the upgrade path wherever the range touched it:
       config migration (`src/github_orchestrator/settings/_config.py`,
       `_renamed_keys.py`), `install.sh` and `src/github_orchestrator/cli/_update.py`.
    6. `/security-review` of the range.
    7. `/adversarial-stress-test` against the live board, after `make restart-all`
       so it runs `main`.

    Reviews 4 to 6 only read, so they can run in parallel. Run 7 on its own,
    since it drives the running board.

04. Triage every finding. A finding is confirmed when it is reproduced or read in
    the code, and when it breaks behaviour, the upgrade path or the docs, or leaks
    private information. Fix each confirmed one through `normal-workflow` and push
    it with `push-properly`. File every other finding as a GitHub issue whose body
    starts with 🤖, and keep the links for step 8.

05. Draft the notes. Group the range's commits by what a user sees: new, changed
    and fixed. Leave out tests, refactors, specs and anything else that changes
    nothing for a user. Write each entry as a user would say it, not as the commit
    subject. Save the draft as `notes.md` in the scratchpad.

06. Bump the version through `normal-workflow`, in one commit named
    `release X.Y.Z`. Set it in `pyproject.toml`, in
    `plugins/pr-summary/.claude-plugin/plugin.json` (the plugin follows the
    release), and in `uv.lock` with `uv lock`. Push it with `push-properly`. A
    pushed bump publishes nothing; only the tag does.

07. Run the pre-release workflow on the bump:
    `gh workflow run pre-release.yml --ref main`. Then
    `gh run list --workflow pre-release.yml --limit 1 --json databaseId,headSha,url`
    gives its id and the commit it runs on. Keep that commit as `SHA`: it is the
    one the tag goes on, even if `main` moves on. Wait with
    `gh run watch <id> --exit-status`, run in the background. Every job must pass.
    When one fails, read `gh run view <id> --log-failed`, fix the cause through
    `normal-workflow`, push with `push-properly`, and run this step again.
    `update-command` skips with a notice while the last release predates
    `GITHUB_ORCHESTRATOR_RELEASES_API`. Pass that notice on in step 8, since then
    only `update-from-previous` tests `update`, after publishing.

08. Stop and show the user:

    - the version, and the commits that decided it;
    - the notes draft;
    - each finding, with what was fixed and the issue links for the rest;
    - the passing pre-release run's URL and `SHA`;
    - anything a review or a job could not run.

    Wait for "go". Apply the user's edits to `notes.md` first.

09. On go, tag `SHA` and push the tag:
    `git tag -a vX.Y.Z -F <notes.md> <SHA>`, then `git push origin vX.Y.Z`.
    Watch the run: `gh run list --workflow Release --branch vX.Y.Z` gives its id,
    and `gh run watch <id> --exit-status`, run in the background, waits for it.

10. When the release run fails, check whether it published, with
    `gh release view vX.Y.Z`.

    - **Not published.** Nobody can have installed the version. Show the
      failure and ask before deleting the tag; deleting a pushed tag is
      destructive. Then delete it with `git push origin :refs/tags/vX.Y.Z` and
      `git tag -d vX.Y.Z`. Fix through `normal-workflow`, push with
      `push-properly`, and go back to step 7.
    - **Published.** Never change a published version. Fix through
      `normal-workflow` and release the next patch version, starting from step 2
      with the range from `vX.Y.Z`.

11. Done when the Release run is green, including `install-the-release` and
    `update-from-previous`. Report the release URL.
