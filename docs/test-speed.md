# Test speed

`make test` runs the whole python suite and the whole Ember suite together.
This is how fast it should stay. It may drift a little slower as features
land, up to about 20% on the median, but a bigger slip means something
grew that should be made cheaper or deleted.

Every test still runs: speed comes from making tests cheaper or deleting ones
that repeat another test's coverage, never from selecting or skipping tests.

## Measuring

`make measure-test-speed` does one priming run, three **cold** runs (each after
at least a minute's rest with the CPU at or below 65 °C) and five **warm** runs
back to back. It prints one JSON line per run with the load average and CPU
temperature taken just before it, then the median and range of each kind.

Timings on this machine swing with load: a fanless laptop throttles when
hot, and every process spawned elsewhere costs the suite kernel time. Measure
with no other test runs or agents going, and compare against a baseline taken at
a similar load. On macOS the load average tracks process spawning more than CPU
use.

## Baseline

| Date       | Commit   | Python tests | Ember tests | Cold median (range) | Warm median (range) | Load before runs | CPU before runs |
| ---------- | -------- | ------------ | ----------- | ------------------- | ------------------- | ---------------- | --------------- |
| 2026-09-30 | d7085b6e | 3,812        | 674         | 8.5 s (8.4-8.5)     | 7.9 s (7.7-8.3)     | 3.5-10.5         | 48-83 °C        |
| 2026-09-30 | b9068a31 | 3,827        | 708         | 8.7 s (8.2-8.9)     | 8.3 s (8.2-9.2)     | 3.1-10.7         | 42-82 °C        |
| 2026-10-01 | b3e86c12 | 3,860        | 721         | 8.6 s (8.4-9.3)     | 9.1 s (8.7-9.6)     | 11.4-17.9 (warm) | 73-89 °C (warm) |
| 2026-10-01 | d232c74e | 4,006        | 739         | 9.4 s (9.1-9.5)     | 9.1 s (8.9-9.5)     | 3.9-17.5         | 38-76 °C        |
| 2026-10-08 | bb8bb958 | 4,154        | 858         | 12.4 s (12.2-12.6)  | 13.6 s (12.3-13.8)  | 4.5-21.5         | 62-91 °C        |
| 2026-10-08 | 1b4f5b90 | 4,298        | 874         | 13.4 s (13.1-14.1)  | 26.5 s (21.7-28.0)  | 5.8-103.8        | 57-83 °C        |
| 2026-10-09 | 38fa9bb7 | 4,281        | 874         | 13.5 s (12.9-14.6)  | 13.1 s (12.7-13.6)  | 5.2-16.0         | 55-87 °C        |
| 2026-10-09 | 216f2ff0 | 4,077        | 930         | 13.4 s (13.4-13.5)  | 13.1 s (12.9-13.8)  | 5.0-26.8         | 53-88 °C        |
| 2026-10-09 | 79a83a65 | 4,077        | 930         | 12.1 s (11.8-12.6)  | 13.7 s (13.0-15.9)  | 2.1-14.7         | 45-92 °C        |
| 2026-10-09 | bd632429 | 4,105        | 930         | 13.2 s (12.4-16.4)  | 12.8 s (12.4-14.9)  | 5.8-15.0         | 47-91 °C        |

The 2026-10-09 row, after the last step of the front-end store plan, matches the cold median above it (13.5 s against 13.4 s) and brings the warm median back to the cold one. Other sessions held the load at 9-16 during the runs.

The second 2026-10-09 row, after the one-command install plan, matches the row above it on both medians. The plan deleted more Python tests (tmux mode, cron, `make install`) than it added.

Since 2026-10-01 the suite is about 30% slower. Three causes are known. (1) bd632429 fixed the largest: six installer tests wrote new stub executables, macOS spent about 0.35 s checking each new executable on its first run, and the six shared one `--forks` chunk, so one child ran to 10.6 s while the rest finished at 4.5 s. Alternating at the same load, the python run alone took 10.8-16.5 s before it and 7.5-8.5 s after. (2) Inside `make test` the python half takes about 12 s against about 8 s alone: the Ember suite, 739 tests then and 930 now, runs beside it and competes for the CPU. (3) Before the installer tests arrived, the python run alone was already 7.5 s on 79a83a65 against 5.2-5.9 s on d232c74e, while `pytest -n 8` and summed per-test time were unchanged; not yet found. `tests/test_makefile_restart_all.py` also waits a deliberate second to prove a second restart-all blocks on the lock. A per-fork timeline plugin for finding the next tail is easy to write: record each test's start, end and pid, and compare when each fork finishes.

The second 2026-10-08 row, after the reply and ticket proposals plan, compares on its cold runs only: those ran at load 5.8-6.4, like the row above, and are about 8% slower. The warm runs are not comparable. Other sessions drove the load from 10.6 to 103.8 while they ran, and one python test failed only in the run at load 87; it is left out of the median.

Machine: a fanless laptop on AC power. `PYTEST_WORKERS` 8, 2 Ember browsers.

The 2026-09-30 runs, in order (seconds):

| Run   | Wall | Python part | Load | CPU   | Result                 |
| ----- | ---- | ----------- | ---- | ----- | ---------------------- |
| prime | 9.0  | 8.4         | 2.4  | 52 °C | pass                   |
| cold  | 8.5  | 8.0         | 3.5  | 50 °C | pass                   |
| cold  | 10.5 | 8.3         | 3.9  | 55 °C | one python test failed |
| cold  | 8.4  | 7.9         | 3.9  | 60 °C | pass                   |
| warm  | 8.3  | 7.8         | 3.8  | 48 °C | pass                   |
| warm  | 7.7  | 7.3         | 5.9  | 70 °C | pass                   |
| warm  | 7.9  | 7.6         | 8.2  | 77 °C | pass                   |
| warm  | 7.8  | 7.5         | 9.9  | 81 °C | pass                   |
| warm  | 8.3  | 8.0         | 10.5 | 83 °C | pass                   |

The failed cold run is a python test that fails only now and then while Ember
runs beside it; six python-only runs straight after all passed. Its time is left
out of the medians.

Under an ordinary working load (other sessions, the orchestrator's own
instances, a call) the same suite took about 10.5-13 s.

Add a row when a multi-step feature finishes (see
`.claude/skills/run-plan-steps`), keeping the older rows.
