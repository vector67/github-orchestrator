#!/usr/bin/env bash
set -uo pipefail

# Tests for rebase-on-main.sh tier resolution and gh account resolution.
#
# Uses --dry-run (which prints GH_USER=/TIER=/BASE=/CMD= and performs no git
# mutations) plus a stub `gh` on PATH, so no network or real stack is needed.

SCRIPT="$(cd "$(dirname "$0")" && pwd)/rebase-on-main.sh"
failures=0
tmproot=$(mktemp -d)
trap 'rm -rf "$tmproot"' EXIT

# --- stub gh -----------------------------------------------------------------
# Behaviour driven by env vars:
#   FAKE_ACCOUNTS    space-separated logged-in accounts; the first one is active
#   FAKE_ACCESS_USER space-separated accounts allowed to read the repo
#                    (default: the active one; set empty to lock everyone out)
#   FAKE_STACK_EXIT  exit code for `gh stack view` (default 2 = not in a stack)
#   FAKE_PR_FAIL     if set, `gh pr view` exits 1 (no PR for this branch)
#   FAKE_BASE        baseRefName printed by `gh pr view` (default main)
mkdir -p "$tmproot/bin"
cat >"$tmproot/bin/gh" <<'STUB'
#!/usr/bin/env bash
read -r -a accounts <<<"${FAKE_ACCOUNTS:-vector67 monalisa}"
active="${accounts[0]}"
access="${FAKE_ACCESS_USER-$active}"
effective="$active"
[[ -n "${GH_TOKEN:-}" ]] && effective="${GH_TOKEN#token-}"

known() {
    local a
    for a in "${accounts[@]}"; do [[ "$a" == "$1" ]] && return 0; done
    return 1
}
has_access() {
    local a
    for a in $access; do [[ "$a" == "$effective" ]] && return 0; done
    return 1
}

case "${1:-} ${2:-}" in
  "auth status")
      echo "github.com"
      for a in "${accounts[@]}"; do
          echo "  * Logged in to github.com account $a (keyring)"
          if [[ "$a" == "$active" ]]; then
              echo "  - Active account: true"
          else
              echo "  - Active account: false"
          fi
      done
      ;;
  "auth token")
      user="$active"
      [[ "${3:-}" == "--user" ]] && user="${4:-}"
      known "$user" || exit 1
      echo "token-$user"
      ;;
  "repo view")
      has_access || exit 1
      echo "owner/repo"
      ;;
  "stack view") exit "${FAKE_STACK_EXIT:-2}" ;;
  "pr view")
      has_access || exit 1
      [[ -n "${FAKE_PR_FAIL:-}" ]] && exit 1
      echo "${FAKE_BASE:-main}"
      ;;
  *) exit 0 ;;
esac
STUB
chmod +x "$tmproot/bin/gh"
export PATH="$tmproot/bin:$PATH"

# --- fixture repo ------------------------------------------------------------
# main <- parent-branch <- feature, all pushed to a bare origin.
make_repo() {
    local dir="$tmproot/repo-$1"
    local bare="$tmproot/origin-$1.git"
    git init -q --bare "$bare"
    git init -q -b main "$dir"
    git -C "$dir" config user.email t@example.com
    git -C "$dir" config user.name Test
    git -C "$dir" commit -q --allow-empty -m "base commit"
    git -C "$dir" remote add origin "$bare"
    git -C "$dir" push -q -u origin main

    git -C "$dir" checkout -q -b parent-branch
    git -C "$dir" commit -q --allow-empty -m "parent work"
    git -C "$dir" push -q -u origin parent-branch

    git -C "$dir" checkout -q -b feature
    git -C "$dir" commit -q --allow-empty -m "feature work"
    git -C "$dir" push -q -u origin feature
    echo "$dir"
}

# --- assertions --------------------------------------------------------------
check() {
    local name="$1" expected="$2" actual="$3"
    if [[ "$actual" == *"$expected"* ]]; then
        echo "PASS: $name"
    else
        echo "FAIL: $name"
        echo "  expected to contain: $expected"
        echo "  actual: $actual"
        failures=$((failures + 1))
    fi
}

# --- tier resolution tests ---------------------------------------------------

# Tier 3: PR targets main -> plain rebase on main, as today.
repo=$(make_repo t3)
out=$(cd "$repo" && FAKE_BASE=main "$SCRIPT" --dry-run 2>&1)
check "tier 3 selected for main base" "TIER=3" "$out"
check "tier 3 base is main" "BASE=main" "$out"
check "tier 3 uses plain rebase" "CMD=git rebase main" "$out"

# Tier 3 fallback: no PR -> falls back to main, but says so.
repo=$(make_repo nopr)
out=$(cd "$repo" && FAKE_PR_FAIL=1 "$SCRIPT" --dry-run 2>&1)
check "no-PR falls back to tier 3" "TIER=3" "$out"
check "no-PR warns about fallback" "could not determine PR base" "$out"

# Tier 2: PR targets a feature branch, no local stack tracking -> fork-point --onto.
repo=$(make_repo t2)
parent_tip=$(git -C "$repo" rev-parse parent-branch)
out=$(cd "$repo" && FAKE_BASE=parent-branch "$SCRIPT" --dry-run 2>&1)
check "tier 2 selected for non-main base" "TIER=2" "$out"
check "tier 2 base is the parent branch" "BASE=parent-branch" "$out"
check "tier 2 rebases onto remote parent" "CMD=git rebase --onto origin/parent-branch $parent_tip" "$out"

# Tier 1: branch is in a locally-tracked stack -> delegate to gh stack.
repo=$(make_repo t1)
out=$(cd "$repo" && FAKE_STACK_EXIT=0 FAKE_BASE=parent-branch "$SCRIPT" --dry-run 2>&1)
check "tier 1 selected when in a stack" "TIER=1" "$out"
check "tier 1 delegates to gh stack" "CMD=gh stack rebase --downstack" "$out"

# --- gh account resolution tests ---------------------------------------------

# The active account can read the repo -> use it, no probing.
repo=$(make_repo ghactive)
out=$(cd "$repo" && "$SCRIPT" --dry-run 2>&1)
check "active account is reported" "GH_USER=vector67" "$out"

# Active account locked out -> probe finds the account that can read the repo,
# and the base resolves through it instead of silently falling back to main.
repo=$(make_repo ghprobe)
out=$(cd "$repo" && FAKE_ACCESS_USER=monalisa FAKE_BASE=parent-branch "$SCRIPT" --dry-run 2>&1)
check "probe picks the account with access" "GH_USER=monalisa" "$out"
check "probe reports the active account is locked out" "cannot read this repo" "$out"
check "base resolved through the probed account" "BASE=parent-branch" "$out"

# --gh-user pins an account even when the active one has access.
repo=$(make_repo ghpin)
out=$(cd "$repo" && FAKE_ACCESS_USER="vector67 monalisa" FAKE_BASE=parent-branch \
    "$SCRIPT" --gh-user monalisa --dry-run 2>&1)
check "--gh-user pins the account" "GH_USER=monalisa" "$out"
check "--gh-user resolves the base" "BASE=parent-branch" "$out"

# Flag order does not matter.
repo=$(make_repo ghorder)
out=$(cd "$repo" && "$SCRIPT" --dry-run --gh-user monalisa 2>&1)
check "--gh-user accepted after --dry-run" "GH_USER=monalisa" "$out"

# --gh-user naming an account that is not logged in is an error.
repo=$(make_repo ghbaduser)
out=$(cd "$repo" && "$SCRIPT" --gh-user nobody --dry-run 2>&1)
rc=$?
check "unknown --gh-user is an error" "no gh account" "$out"
[[ $rc -ne 0 ]] || { echo "FAIL: unknown --gh-user should exit nonzero"; failures=$((failures + 1)); }

# No logged-in account can read the repo -> say so, and flag the main fallback
# as untrustworthy rather than reporting it as the real base.
repo=$(make_repo ghnoaccess)
out=$(cd "$repo" && FAKE_ACCESS_USER= "$SCRIPT" --dry-run 2>&1)
check "no readable account is reported" "GH_USER=none" "$out"
check "no readable account warns" "no logged-in gh account can read" "$out"
check "unknown base is called unknown" "UNKNOWN, not main" "$out"

# --- guards ------------------------------------------------------------------

# Guard: refuse to run on main.
repo=$(make_repo onmain)
git -C "$repo" checkout -q main
out=$(cd "$repo" && "$SCRIPT" --dry-run 2>&1)
rc=$?
check "on main is an error" "checkout a feature branch first" "$out"
[[ $rc -ne 0 ]] || { echo "FAIL: on main should exit nonzero"; failures=$((failures + 1)); }

# Guard: refuse to run with a rebase in progress.
repo=$(make_repo inprogress)
mkdir -p "$(git -C "$repo" rev-parse --absolute-git-dir)/rebase-merge"
out=$(cd "$repo" && "$SCRIPT" --dry-run 2>&1)
rc=$?
check "rebase in progress is an error" "rebase is still in progress" "$out"
[[ $rc -ne 0 ]] || { echo "FAIL: rebase in progress should exit nonzero"; failures=$((failures + 1)); }

echo
if [[ $failures -eq 0 ]]; then
    echo "All tests passed."
else
    echo "$failures test(s) failed."
    exit 1
fi
