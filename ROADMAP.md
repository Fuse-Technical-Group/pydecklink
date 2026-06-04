# pydecklink Roadmap

Derived from [SPEC.md](SPEC.md). Sections are in build-dependency order.

## Allocator cleanup

- **split-pooled-buffer-handle**: Refactor `ManagedBuffer` into a
  pure-data `PooledBuffer` (memory + size, owned by the allocator's
  free-list) and a per-issuance `BufferHandle` (implements
  `IDeckLinkVideoBuffer`, standard COM semantics, dtor returns
  `PooledBuffer*` to the free-list). Restores standard COM
  refcount semantics — `Release()→0` destroys the handle instead
  of the current "refcount==0 still valid memory" exception that
  fights `ComPtr`. Removes `revive()`, the manual AddRef/Release
  pair in ctor/Release, and the `ManagedBuffer*` raw-owning
  free-list. Per-issuance `new BufferHandle` is a tiny heap object
  (no syscall) — the pool still amortizes the expensive `cudaHostAlloc`.
  Hardware regression: existing `TestCustomAllocatorZeroCopy` plus a
  4K59.94/10-bit loopback run. Raised in PR #110 review (#110 lands
  the recycling design as-is; this workstream closes the COM-semantics
  gap).

## Supply chain

Closes SPEC §10. Build-order rationale: Dependabot and the
pin-shape lint are both independent of scanning and lowest risk;
either can land first. The PR-time gate proves the
`osv-scanner.toml` severity threshold and suppression policy
end-to-end against a real PR; the scheduled audit reuses that
config so it lands next. `dependency-review-action` is a UX
refinement on top of the working gate. `scorecard-action` is a
separate axis (self-audit, not dep-scan) and lowest priority.

- **dependabot-config**: Add `.github/dependabot.yml` covering the
  `pip` and `github-actions` ecosystems on a weekly cadence,
  grouping patch/minor updates. No scanning involved — this is the
  bumping arm. §spec:10
- **actions-pin-shape-lint**: Add a `pin-shape` step to
  `lint-docs.yml` that fails the workflow if any external `uses:`
  reference under `.github/workflows/**.yml` does not match the
  shape `<owner>/<repo>@<40-char-sha>` followed by a `# vX.Y.Z`
  point-version comment. Local references (`uses: ./...`) are
  exempt. Implementation is a single shell step (grep + awk, no
  new dependency) and runs in well under a second. Independent of
  vulnerability scanning — catches structural drift back toward
  floating major tags regardless of whether the action has an
  advisory. §spec:10
- **osv-scanner-pr-gate**: Add a PR-time `google/osv-scanner-action`
  job to `ci-linux.yml`, running parallel to the existing
  `lint`/`compile` jobs. Scans the `uv.lock` Python closure and
  `.github/workflows/` action references against OSV.dev. Fails the
  job on HIGH/CRITICAL advisories; reports MEDIUM/LOW as job
  annotations. Configure threshold and suppression policy in
  `osv-scanner.toml` at repo root, with the `expires` field required
  on every ignore entry. PR-time budget: <30s. §spec:10
- **dependency-review-pr-ux**: Add `actions/dependency-review-action`
  to a `dependency-review.yml` workflow on `pull_request`. Surfaces
  the dep delta (Python + Actions added/upgraded by the PR) as PR
  review-UI annotations rather than a single CI status. Reuses the
  HIGH/CRITICAL threshold from `osv-scanner.toml`. Depends on
  osv-scanner-pr-gate. §spec:10
- **scheduled-osv-audit**: Add a weekly cron workflow
  (`vuln-audit.yml`) that runs `osv-scanner` against current `main`
  and uploads SARIF to the GitHub Security tab. Reuses
  `osv-scanner.toml`. Reports do not fail anything — they surface
  advisories that dropped after merge for triage. Depends on
  osv-scanner-pr-gate. §spec:10
- **scorecard-self-audit**: Add `ossf/scorecard-action` scheduled
  workflow (`scorecard.yml`) producing an OpenSSF Scorecard report
  for this repo, uploaded as SARIF to the GitHub Security tab.
  Independent of dep-scanning — answers "is *pydecklink* hardened?"
  rather than "are pydecklink's deps vulnerable?". Lowest priority
  in the section. §spec:10
- **migrate-release-please-to-flywheel**: Replace release-please with
  point-source/flywheel for versioning and release automation, matching
  the org standard (humongous-boat); removes `release-please.yml`,
  `release-please-config.json`, `.release-please-manifest.json`, adds
  `.flywheel.yml` + flywheel PR/push workflows, switches `pyproject.toml`
  to a dynamic version from the git tag (setuptools_scm), and rewires
  `build-wheels.yml` to trigger on the release-tag push, attach wheels to
  the draft, and publish only after all platforms succeed. §spec:10.
  Unblocked — flywheel ≥ v1.4.0 supports per-branch `release_as_draft`
  (its `§spec:immutable-release-support`), satisfying the §10 draft →
  attach → promote requirement; set it on `main`. PyPI/index distribution
  remains out of scope (staying on immutable GitHub Release assets).

**Verify:** End-to-end coverage of §10 is observable via five
surfaces:

- *Pin-shape lint.* Open a PR that adds an external Action
  reference of the form `actions/checkout@v5` (no SHA) to any
  workflow. The `pin-shape` lint job fails with a pointer to the
  offending file:line. Replacing the reference with
  `actions/checkout@<sha> # v5.x.y` restores green.
- *PR-time gate.* Open a PR that adds a known-vulnerable Python or
  Action reference (e.g. pin `requests==2.19.0` for the test, then
  remove). The `osv-scanner` CI job fails with an advisory ID
  (`GHSA-...` or `CVE-...`), affected package, and fixed version.
  Removing the pin restores green.
- *Bump arm.* Within one week of merge, Dependabot opens at least
  one PR titled `chore(deps):` or `build(deps):` against a stale
  pin in `pyproject.toml` or a workflow file.
- *Scheduled audit.* The weekly `vuln-audit.yml` run completes and
  any current advisories appear in the repo's GitHub Security tab
  under "Code scanning alerts".
- *Self-audit.* The weekly `scorecard.yml` run completes and the
  OpenSSF Scorecard score appears in the Security tab; the public
  badge at `https://api.securityscorecards.dev/projects/github.com/Fuse-Technical-Group/pydecklink`
  reflects the latest scan date.

## Future

- **hdr-metadata**: `IDeckLinkVideoFrameMutableMetadataExtensions`
  for HDR10/HLG output. Required for bmd-signal-gen integration
  (Spec §8).
- **audio-streams**: Audio capture/playout via
  `ScheduleAudioSamples` / `IDeckLinkAudioInputPacket`.
- **ancillary-data**: Timecode, closed captions.
