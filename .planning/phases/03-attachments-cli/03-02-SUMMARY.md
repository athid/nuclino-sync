---
phase: 03-attachments-cli
plan: 02
subsystem: cli
tags: [typer, dry-run, error-reporting, cli]

# Dependency graph
requires:
  - phase: 03-01
    provides: attachment upload function and tests
  - phase: 02-import-core
    provides: run_import, state management, API client
provides:
  - "--dry-run CLI flag for previewing imports without API calls"
  - "Post-run failure summary printed to stdout"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["dry-run preview pattern (iterate notes, print plan, no API calls)"]

key-files:
  created: []
  modified: [sync.py, tests/test_api.py]

key-decisions:
  - "Dry-run dispatched before API key check so it works without credentials"
  - "Failure summary reads from state dict post-loop rather than tracking separately"

patterns-established:
  - "Preview mode pattern: iterate discover_notes, print per-note action, summary line"

requirements-completed: [CFG-01, CFG-02, CFG-03, CFG-04]

# Metrics
duration: 2min
completed: 2026-03-21
---

# Phase 03 Plan 02: CLI Dry-Run and Failure Summary

**--dry-run flag previews import plan without API calls; post-run failure summary surfaces errors to stdout**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-21T17:27:48Z
- **Completed:** 2026-03-21T17:30:02Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `run_dry_run()` function that previews what would be imported (title, folder, attachment count) without any API calls
- Added `--dry-run` CLI flag that works without `NUCLINO_API_KEY` set
- Added post-run failure summary to `run_import()` that prints failed note paths and errors to stdout
- 5 new tests (4 dry-run + 1 failure summary), total suite now 63 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --dry-run flag and run_dry_run function** - `94b2f6f` (feat)
2. **Task 2: Add post-run failure summary to run_import** - `8a87cb1` (feat)

## Files Created/Modified
- `sync.py` - Added `run_dry_run()` function, `--dry-run` CLI flag, and post-run failure summary in `run_import()`
- `tests/test_api.py` - Added `TestDryRun` class (4 tests) and `TestFailureSummary` class (1 test)

## Decisions Made
- Dry-run dispatched before API key check so `--dry-run` works without credentials (follows same pattern as `--parse-only`)
- Failure summary reads failed items from the state dict after the import loop completes, avoiding separate tracking

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 03 (attachments-cli) is complete: attachment upload, dry-run mode, and failure reporting all implemented
- Ready for Phase 04 (final polish / verification)

---
*Phase: 03-attachments-cli*
*Completed: 2026-03-21*
