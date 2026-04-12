# Scope

database is the knowledge core of a future biodiversity learning product.
It builds an internal canonical reference of living taxa, ingests traceable real-world naturalist data, and qualifies media for pedagogical reuse.
External sources feed the system, but do not define its internal identity.
Raw observations and images are not yet learning resources; they become usable only after qualification.
Qualification is evidence- and pedagogy-driven: what is visible, what can be learned, and what is reliable enough to reuse.
The system is designed to automate most of this work while keeping uncertain cases reviewable.
Its job is to turn observed reality into a canonical, traceable, exportable corpus for future learning experiences.
The current implementation is an intentionally narrow pilot: birds-only, iNaturalist-first, image-only.
That narrow scope is a proving ground for a structure meant to scale toward a broader multi-taxa knowledge core.
Canonical governance for phase 1 is defined in `docs/06_charte_canonique_v1.md`.

## Current baseline

The repository is at a useful Gate 9 baseline and already includes:

- playable surface persistence and inspection
- pack specifications, immutable revisions, and diagnostics
- compiled pack builds and frozen materializations
- asynchronous enrichment queue persistence
- batch confusion ingestion and global aggregates

- KPI/smoke/CI discipline around the current contracts

The cumulative incremental playable lifecycle is now implemented (`active`/`invalidated`) and served through `playable_corpus.v1` without global reset semantics.
The remaining structural focus is improving invalidation reason precision and keeping storage responsibilities decomposed.

Historical checkpoint:

- during Gate 4.5, corrective sequencing was locked before extension work.
- cumulative incremental playable corpus remains the reference posture for serving stability.

Current scope:

- internal canonical bird taxonomy objects
- traceable upstream-shaped observation and media records
- cached real-world iNaturalist snapshots
- explicit canonical enrichment from cached taxon payloads
- qualification for pedagogical reuse
- structured review queue plus snapshot-scoped review overrides
- deterministic pack compilation and frozen materializations
- asynchronous enrichment request and execution tracking
- batch confusion ingestion plus global confusion aggregates
- explicit traceability of compiled build history and materialization lineage
- export of only qualified resources
- PostgreSQL/PostGIS storage and CLI inspection

Current non-goals:

- quiz runtime
- frontend product work
- user progression
- business logic
- institution features
- full-scale ingestion
- runtime session/scoring/progression
- adaptive runtime orchestration
- user-facing serving APIs

Phase 1 stays intentionally small:

- bird-only
- iNaturalist-only source implementation
- image-only media qualification
- research-grade source quality only
- commercial-safe export only
- pilot seed list of 15 bird taxa

The first fixture dataset remains tiny on purpose.
It validates the data model, enrichment flow, qualification stages, review workflow, and export contract before live harvesting is expanded further.
