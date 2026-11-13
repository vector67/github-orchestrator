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
| 2026-10-15 | db18876b | 4,315        | 961         | 11.5 s (11.1-11.9)  | 11.7 s (11.0-11.9)  | 2.6-13.2         | 46-91 °C        |
| 2026-10-23 | 817b7d6a | 4,598        | 1,157       | 9.5 s (9.4-9.8)     | 10.0 s (9.3-10.1)   | 1.9-8.1          | 51-90 °C        |
| 2026-11-12 | 21094fe6 | 5,571        | 1,677       | 22.6 s (22.3-24.9)  | 29.1 s (22.9-40.1)  | 3.8-12.3         | 53-81 °C        |
| 2026-11-13 | 5948e26b | 5,642        | 1,679       | 17.3 s (16.6-17.3)  | 21.6 s (18.1-64.9)  | 3.6-34.5         | 54-86 °C        |

The 2026-11-13 row closes the speed round #402. Measured the same way at 341ed0ba just before it, at load 3.1-8.3, the cold median was 22.4 s (21.5-22.8) and the warm one 24.8 s (21.2-43.6). Most of the rise since 2026-10-23 was one test: `test_the_preview_removes_its_folder_when_ctrl_c_stops_it` ran `preview.main` live, about 364 git spawns, because its folder had a new random name every run and no recording could match it. It shared a fork with the rest of the preview file, and its spawns slowed every other fork: the python suite alone took 25.7 s, and 9.6 s with it and the other live preview test left out. It now names its folder and replays, and the python suite alone takes about 10-11 s. The toast undo tests waited out the board's real 500 ms settling pause and now tick the fake clock (3.2 s of one browser's time down to 0.1 s), and only the preview tests that share a seeded board stay in one fork.

Inside `make test` the python half now finishes last, at about 16-17 s, with every fork busy to the end. Four files hold half of its 109 s of fork time: the preview 31 s, the server 10 s, terminal sessions 9 s and the summary lane 7 s. `test_the_preview_lands_its_seeded_fixes_where_git_has_no_identity` has to run git for real, so its own 364 spawns take 14 s in one fork, about as long as the other forks run; seeding the preview, live or replayed, is the cost of the board's own code writing its records. The Ember half alone takes about 10.6 s on a quiet machine, with no single test over 150 ms. Weighing its partitions again changed nothing measurable, and a trial of 3 browsers ran at load 19-75 and showed nothing either way, so `TEST_BROWSERS` stays 2. The warm runs climbed from load 4.9 to 34.5 as they ran back to back, so only the cold median compares.

The 2026-11-12 row closes the click consistency plan (#366). The same measurement at d12180c4, the commit before the plan, at the same load, gave a cold median of 22.5 s (22.3-22.8) and a warm one of 26.0 s (21.8-41.0), so the plan added no measurable time. The rise from the 2026-10-23 row came from the features between them, which added no row.

The 2026-10-23 row closes the speed rounds #140-#144 and brings the cold median under 10 s with 283 more python and 196 more Ember tests than the row above. Alone, the python half takes about 5.1 s and the Ember half about 6.9 s; together they compete for the 4 performance cores, so the next cut has to come from the Ember half, which now finishes last. Fork counts of 4, 6 and 8 made no clear difference, so `PYTEST_WORKERS` stays 8.

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
