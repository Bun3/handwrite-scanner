# Portable work implementation plan

**Goal:** Move saved templates and jobs between PCs, delegate selected unfinished pages, and merge returned results with explicit page conflict choices.

**Architecture:** Versioned `.hscan` ZIP packages contain declarative JSON and required image/original files. Jobs own immutable template snapshots and stable lineage/page IDs. Import is staged and validated before creating new local jobs; merging produces a new combined job, preserving both inputs as recoverable copies. Workers support sparse completed pages only for jobs with validated page identity metadata.

**Tech stack:** Existing FastAPI, filesystem JSON, zipfile/hashlib, vanilla JS dialogs and Playwright/pytest. No additional runtime dependency.

**Spec:** Approved conversation on 2026-09-18: template/job transfer first; page delegation and result merging; explicit conflict resolution, no silent overwrite, manual resume, model binaries excluded. Existing jobs snapshot current templates with a visible legacy notice. Unsaved browser drafts and unsubmitted uploads are out of scope.

## Constraints
- Preserve unrelated model benchmark changes; no deployment until requested.
- Saved templates, reference images, original inputs, selected pages and reviewed results travel together.
- New jobs freeze templates at creation; explicit rerun refreshes templates for ordinary local jobs, imported jobs retain their private snapshots.
- Active work must stop before export, delegation or merge. Import never auto-runs.
- Same-name different-template import creates a distinct name. Duplicate package jobs are skipped unless explicitly copied.
- Match merged pages by lineage + page identity + input hash + template digest; never by filename alone.
- Conflicting page results require a per-page choice. Merge is a new combined job; neither input is overwritten.
- Validate format version, paths, sizes, JSON, image payloads and checksums before publishing imports. Bound archive size/entries; stream files on disk.

## Tasks
- [x] Add tests for frozen templates, transfer roundtrip, split/merge, sparse resume, conflict decisions, duplicate imports and malformed archives.
- [x] Implement `app/job_context.py`: template snapshots, original model identity, stable page IDs and input digests.
- [x] Implement `app/transfer.py` plus archive helper: previewable `.hscan` export/import; collision-safe local publication; returned-result merge into a new job.
- [x] Add transfer API router before static mount. Guard active jobs, expose preparation/splitting and release-assignment actions, keep export files on disk.
- [x] Adapt worker/resume/field edits for sparse imported results; preserve source page mappings and original snapshots.
- [x] Add `transfer.html` and `transfer.js`: template/job selection, stop-and-export, page delegation, import preview, model guidance, conflict comparison and completion links.
- [x] Verify API roundtrips using separate isolated PC directories and browser flows. Run existing regression suite, document user-facing behavior and practical limits.
