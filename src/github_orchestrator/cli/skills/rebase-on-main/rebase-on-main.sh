#!/usr/bin/env bash
set -euo pipefail

# Rebase current feature branch on the base its PR actually targets.
# Exits with code 1 if conflicts need manual resolution.

usage() {
    cat <<'USAGE'
Usage: rebase-on-main.sh [--gh-user <account>] [--dry-run] [--help]

Resolves which gh account can read this repo, then resolves the base the current
branch should be rebased on, then rebases.

Account resolution, in order:

  1. --gh-user <account>: use that account's token, no probing.
  2. The active gh account, if it can read this repo.
  3. Each other logged-in account, in order, until one can read this repo.
  4. None of them: prints GH_USER=none. The PR base is then UNKNOWN, and the
     fall back to main must not be trusted.

Tier resolution, in order:

  1. Branch is in a locally-tracked GitHub stack (`gh stack view` succeeds):
     delegate to `gh stack rebase --downstack`, which rebases trunk and every
     layer below the current branch. Parent branches move locally but are NOT
     pushed.
  2. The PR targets a branch other than the default (a stack without local
     tracking): rebase with --onto from the fork point, so commits belonging to
     the base branch are not replayed.
  3. The PR targets the default branch, or there is no PR: check out main, pull,
     and rebase on it.

If the rebase hits conflicts, exits 1 for manual resolution. Note that tier 1
conflicts must be resumed with `gh stack rebase --continue`, NOT
`git rebase --continue`.

Options:
  --gh-user <account>  Use this logged-in gh account instead of probing for one.
                       Errors if the account is not logged in.
  --dry-run            Print the resolved GH_USER=, TIER=, BASE= and CMD= and
                       exit without fetching, checking out, or rebasing.

Examples:
  rebase-on-main.sh                                 # probe for a readable account
  rebase-on-main.sh --gh-user monalisa              # pin the work account
  rebase-on-main.sh --dry-run                       # show what it would do
USAGE
    exit 0
}

dry_run=false
gh_user=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help) usage ;;
        --dry-run) dry_run=true; shift ;;
        --gh-user)
            [[ -n "${2:-}" ]] || { echo "Error: --gh-user needs an account name" >&2; exit 1; }
            gh_user="$2"; shift 2 ;;
        --gh-user=*) gh_user="${1#*=}"; shift ;;
        *) echo "Error: unknown option: $1" >&2; exit 1 ;;
    esac
done

rebase_in_progress() {
    [[ -d "$(git rev-parse --absolute-git-dir)/rebase-merge" ]] || \
    [[ -d "$(git rev-parse --absolute-git-dir)/rebase-apply" ]]
}

if rebase_in_progress; then
    echo "Error: a rebase is still in progress." >&2
    echo "Resolve conflicts and run: git rebase --continue" >&2
    echo "(or 'gh stack rebase --continue' if the stack tooling started it)" >&2
    exit 1
fi

branch=$(git branch --show-current)

if [[ "$branch" == "main" ]]; then
    echo "Error: already on main — checkout a feature branch first" >&2
    exit 1
fi

# --- resolve the gh account --------------------------------------------------

# Every gh call below (stack view, pr view, stack rebase) has to run as an
# account that can actually see this repo, so this runs before tier resolution.
# Tokens stay inside the pipeline: never echoed, never written to disk.

gh_accounts() {
    gh auth status 2>/dev/null | awk '
        /Logged in to .* account /{ for (i = 1; i <= NF; i++) if ($i == "account") print $(i + 1) }
    ' || true
}

gh_active_account() {
    gh auth status 2>/dev/null | awk '
        /Logged in to .* account /{ for (i = 1; i <= NF; i++) if ($i == "account") acct = $(i + 1) }
        /Active account: true/ { print acct; exit }
    ' || true
}

repo_readable_as() {
    local user="${1:-}"
    if [[ -z "$user" ]]; then
        gh repo view --json nameWithOwner >/dev/null 2>&1
    else
        gh auth token --user "$user" >/dev/null 2>&1 && \
            GH_TOKEN="$(gh auth token --user "$user")" \
                gh repo view --json nameWithOwner >/dev/null 2>&1
    fi
}

active_account=$(gh_active_account)

if [[ -n "$gh_user" ]]; then
    if ! gh auth token --user "$gh_user" >/dev/null 2>&1; then
        echo "Error: no gh account '$gh_user' is logged in." >&2
        echo "       Logged in: $(gh_accounts | tr '\n' ' ')" >&2
        exit 1
    fi
    export GH_TOKEN="$(gh auth token --user "$gh_user")"
    echo "==> Using gh account: $gh_user (pinned with --gh-user)"
elif repo_readable_as ""; then
    gh_user="${active_account:-unknown}"
    echo "==> Using gh account: $gh_user"
else
    for candidate in $(gh_accounts); do
        [[ "$candidate" == "$active_account" ]] && continue
        if repo_readable_as "$candidate"; then
            export GH_TOKEN="$(gh auth token --user "$candidate")"
            gh_user="$candidate"
            echo "==> Active account ${active_account:-<none>} cannot read this repo."
            echo "==> Using gh account: $gh_user"
            break
        fi
    done
    if [[ -z "$gh_user" ]]; then
        gh_user=none
        echo "==> Warning: no logged-in gh account can read this repo" >&2
        echo "    (tried: $(gh_accounts | tr '\n' ' ')). The PR base cannot be read." >&2
    fi
fi

# --- resolve the tier --------------------------------------------------------

# Tier 1: a locally-tracked stack. `gh stack view` exits non-zero both when the
# branch is not in a stack and when the extension is not installed, which is
# exactly the fallback we want in either case.
if gh stack view --json >/dev/null 2>&1; then
    tier=1
    base=$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || echo "")
    cmd="gh stack rebase --downstack"
else
    base=$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || echo "")
    if [[ -z "$base" ]]; then
        if [[ "$gh_user" == "none" ]]; then
            echo "==> Note: could not determine PR base — no logged-in gh account can" >&2
            echo "    read this repo. The base is UNKNOWN, not main. Falling back to" >&2
            echo "    main anyway; re-run with --gh-user <account> before trusting it." >&2
        else
            echo "==> Note: could not determine PR base (no PR for this branch, checked" >&2
            echo "    as $gh_user). Falling back to main." >&2
        fi
        base=main
    fi

    if [[ "$base" == "main" ]]; then
        tier=3
        cmd="git rebase main"
    else
        tier=2
        # --fork-point consults origin/$base's reflog, so commits the base
        # branch amended during its own rebase are not replayed here. Falls
        # back to a plain merge-base when no reflog is available (fresh clone).
        $dry_run || git fetch origin "$base"
        old_base=$(git merge-base --fork-point "origin/$base" HEAD 2>/dev/null) \
            || old_base=$(git merge-base "origin/$base" HEAD)
        cmd="git rebase --onto origin/$base $old_base"
    fi
fi

echo "GH_USER=$gh_user"
echo "TIER=$tier"
echo "BASE=$base"
echo "CMD=$cmd"

if $dry_run; then
    exit 0
fi

# --- run it ------------------------------------------------------------------

echo "==> Current branch: $branch"

case $tier in
    1)
        echo "==> Branch is in a stack. Recording pre-rebase layer SHAs..."
        git for-each-ref --format='%(refname:short) %(objectname)' refs/heads
        echo "==> Cascading rebase from trunk up to $branch..."
        if $cmd; then
            echo "==> Rebase completed successfully"
            echo "==> Post-rebase layer SHAs:"
            git for-each-ref --format='%(refname:short) %(objectname)' refs/heads
        else
            echo ""
            echo "==> Stack rebase paused due to conflicts."
            echo "    Resolve conflicts, then run: git add <files> && gh stack rebase --continue"
            echo "    To back out entirely:        gh stack rebase --abort"
            exit 1
        fi
        ;;
    2)
        echo "==> Rebasing onto origin/$base (from fork point $old_base)..."
        if $cmd; then
            echo "==> Rebase completed successfully"
            echo "==> Note: this branch is not in a locally-tracked stack."
            echo "    'gh stack init' or 'gh stack link' would let gh stack manage it."
        else
            echo ""
            echo "==> Rebase paused due to conflicts."
            echo "    Resolve conflicts, then run: git add <files> && git rebase --continue"
            exit 1
        fi
        ;;
    3)
        echo "==> Checking out main and pulling latest..."
        git checkout main
        git pull
        echo "==> Checking out $branch..."
        git checkout "$branch"
        echo "==> Rebasing on main..."
        if $cmd; then
            echo "==> Rebase completed successfully"
        else
            echo ""
            echo "==> Rebase paused due to conflicts."
            echo "    Resolve conflicts, then run: git add <files> && git rebase --continue"
            exit 1
        fi
        ;;
esac
