---
phase: 04-hardening
plan: 01
subsystem: api
tags: [sanitization, dry-run, placeholder, edge-cases]

# Dependency graph
requires:
  - phase: 03-attachments-cli
    provides: "run_import, run_dry_run, ensure_collection functions"
provides:
  - "sanitize_collection_name function for safe API collection names"
  - "Empty note placeholder import (no more skipped_empty)"
  - "Dry-run pre-flight summary with note/attachment/metadata counts"
affects: [04-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Pre-flight summary before per-note dry-run output", "Placeholder body for empty notes"]

key-files:
  created: []
  modified: ["sync.py", "tests/test_api.py", "tests/test_parse.py"]

key-decisions:
  - "Empty notes imported with '*(empty note)*' placeholder + metadata footer instead of being skipped"
  - "Collection name sanitization uses original string as state key for idempotency"
  - "Dry-run pre-flight scans all notes before per-note loop to compute aggregate counts"

patterns-established:
  - "sanitize_collection_name: replace / with ' - ', & with 'and', strip control chars"
  - "Module-level _sanitized_warnings set for once-per-name warning deduplication"

requirements-completed: [SC-01, SC-02, SC-03]

# Metrics
duration: 4min
completed: 2026-03-21
---

# Phase 4 Plan 1: Hardening Summary

**Collection name sanitization, empty note placeholder import, and dry-run pre-flight summary with aggregate counts**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-21T18:07:38Z
- **Completed:** 2026-03-21T18:12:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added sanitize_collection_name() handling /, &, and control characters with state key preserving original names
- Empty notes now imported with "*(empty note)*" placeholder body + metadata footer instead of being skipped
- Dry-run prints pre-flight summary block before per-note lines showing aggregate counts, attachment info, metadata footer details, and lost frontmatter fields
- 11 new tests added (74 total, up from 63)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add sanitize_collection_name, empty note placeholder, dry-run pre-flight** - `62d676d` (feat)
2. **Task 2: Add tests for sanitization, empty note import, dry-run pre-flight** - `558e7e9` (test)

## Files Created/Modified
- `sync.py` - Added sanitize_collection_name function, updated ensure_collection to sanitize titles, changed empty note handling to placeholder import, added pre-flight summary block to run_dry_run
- `tests/test_api.py` - Added tests for collection sanitization in ensure_collection, empty note placeholder import, dry-run pre-flight summary, updated existing test counts
- `tests/test_parse.py` - Added TestSanitizeCollectionName with 5 test cases

## Decisions Made
- Empty notes use "*(empty note)*" as placeholder body per D-04; metadata footer still appended after
- State key for collections uses original unsanitized name per D-09 for idempotency
- Pre-flight summary scans all notes in a separate loop before per-note output per D-03
- Warning deduplication uses module-level set to log each sanitized name only once per D-10

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_summary_output count from 2 to 3**
- **Found during:** Task 1
- **Issue:** Existing test expected "Imported 2 notes" but empty notes are now imported (3 total)
- **Fix:** Updated assertion to expect "Imported 3 notes"
- **Files modified:** tests/test_api.py
- **Verification:** Full test suite passes
- **Committed in:** 62d676d (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Expected behavioral change in test assertion. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All hardening changes complete and tested
- Ready for Plan 2 (README and final documentation)

---
*Phase: 04-hardening*
*Completed: 2026-03-21*
