---
name: refactor
description: Use for a refactor in this repository — reshaping a type, a signature or a module's seams while what it does stays the same
---

# Refactor

- **Ask how often to stop, not only how much to do.** A multi-phase refactor
  stops for the user after each phase even when every phase is in scope, so a
  scoping question offers both "all four, stop after each" and "all four,
  straight through". An answer that settles only the scope reads as licence to
  run through the lot.

- **Let mypy name the work when a type or signature changes.** Run
  `make lint-python` right after the first production edit, and treat every error
  it reports as the list of what is left. A green suite proves little here: a test
  that patches a producer with `return_value=` keeps feeding the old shape, so a
  reader nobody converted still passes. An edit made only to quiet mypy is still a
  behaviour change until shown otherwise — `.get(k, default)` turned into `[k]`,
  an added `str()` or `cast` — so say what makes each one safe.

- **Repair a broken suite with `--lf`, not repeated full runs.** When a change
  breaks many tests, run the suite once, then iterate with
  `uv run pytest tests/ --lf -n 4 -q` file by file, and return to the full suite
  only when that is green. A full run per fix spends a minute to learn one number.

- **mypy stops at `src`.** After moving code to a new module, run
  `rg '"<old.dotted.path>\.' tests`: a string patch target still naming the old
  module passes lint and patches nothing. After renaming or removing a method on
  an interface or fake, run `rg 'def <old_name>\(' tests` and fix every override
  before running tests: a stale override silently stops matching, and one that
  deferred a callback turned into a deadlock that hung the suite.

- **Sweep tests with `ast` or `libcst`, not regex.** Key a rename or signature
  change on the call or name. A regex cannot tell `"path", line` from
  `"owner/name", n`, and undoing a bad sweep costs more than writing the codemod.

- **When a type replaces a primitive, check what callers print.** If its `str()`
  reads differently from the old value, run `rg '\{<name>\}|%d|%s'` over the
  touched modules and check each rendering: mypy cannot see a changed log line
  or UI string.

- **Diff duplicates before collapsing them.** Where several hand-rolled copies
  become one, every difference between them in logging, error types or what counts
  as corrupt input is a behaviour change for the callers switching over. List each
  one in the commit message.

- **The protective test must pass on the old code first.** Write the test that
  pins the behaviour being preserved, run it green against the unrefactored code,
  and keep it green through the change. An import error for a module that does
  not exist yet is not red. Keep its expected outcomes hand-written: a test that
  iterates the new production table only proves the code agrees with itself.
  When behaviour moves into a new function, the old tests through the old entry
  point are the protective tests: keep them green through the move, break the new
  code on purpose once to see the new tests catch it, and delete the old ones in
  a later commit. Deleting them alongside can drop the wiring only they covered.
