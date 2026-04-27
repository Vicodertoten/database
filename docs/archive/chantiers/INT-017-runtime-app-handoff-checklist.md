# INT-017 Runtime-App Handoff Checklist

Purpose:
- provide an execution checklist for `runtime-app` to close INT-017 consumer-side
- keep wording and UI evidence aligned with owner-side baseline

Consumer-side closure requires all checks below to be marked done.

## 1) Wording unification (README/docs/UI)

- [ ] Remove any remaining wording that suggests the visible runtime is an ID-only technical demonstrator.
- [ ] Keep one visible wording for web: minimal pedagogical player.
- [ ] Keep one visible wording for mobile: minimal real image-first surface.
- [ ] Keep session status wording explicit: runtime sessions are nominal and persisted.
- [ ] Ensure README, execution docs, and in-app labels/tooltips use the same wording.

## 2) Web minimal pedagogical baseline

- [ ] Web question surface renders image as primary content when media is available.
- [ ] Pedagogical metadata remains visible and coherent (`taxon_label`, short feedback context when relevant).
- [ ] No fallback-first behavior that hides image behind technical JSON/ID displays in nominal path.

## 3) Mobile minimal real image-first baseline

- [ ] Mobile question surface renders image in the main visible area (not only URL consumption).
- [ ] UI keeps attribution/license visible or reachable in the immediate flow.
- [ ] Error/fallback state remains user-facing and pedagogical when image load fails.

## 4) Session persistence evidence

- [ ] Provide one nominal evidence trace that sessions persist across app restart/navigation.
- [ ] Confirm docs wording matches observed behavior (no prototype phrasing).

## 5) Integration log synchronization

- [ ] Add INT-017 consumer-side entry/update in `runtime-app/docs/20_execution/integration_log.md`.
- [ ] Reference owner-side INT-017 and confirm no new owner contract/surface was introduced.
- [ ] Mark closure criteria status (`open` until all checks above are done).

## 6) Expected closure note

Use a short closure sentence aligned with owner wording:

"INT-017 closed: visible runtime baseline is now consistently documented and rendered as web minimal pedagogical + mobile minimal image-first, with nominal persisted sessions and no technical-demonstrator ambiguity."
