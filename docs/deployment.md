# Committed releases, staging and activation

The deployment helper builds the **exact requested Git commit**, even when other agents have dirty tracked files, a changed index or untracked work. It does not archive their worktree bytes. Commit finished work before deploying it. The artifact includes runtime source, USD assets and documentation; editable `.blend` binaries remain in Git but are excluded from the GPU runtime artifact.

This is a bounded release mechanism, not a process manager. Staging, source-pointer activation, dependency compatibility, service restart and GPU acceptance are distinct steps. A successful stage or activation proves neither that a process restarted nor that OVStage/OVRTX rendered the new revision.

## Layout

Use a **new dedicated root**, default `/home/horde/park-twin-deploy`. The legacy `/home/horde/park-twin` remains untouched by default.

```text
park-twin-deploy/
  incoming/<commit>-<archive-hash-prefix>/  # upload and committed verifier
  releases/<full-commit>/                  # fresh, verified source/asset tree
    release-manifest.json
    runtime -> ../../shared/runtime
    .venv -> ../../shared/.venv
    backend/data -> ../../../shared/data
  shared/
    runtime/                              # logs, PIDs, local operational files
    data/                                 # SQLite and its companion files
    .venv/                                # explicitly managed compatible environment
  current -> releases/<full-commit>        # optional atomic source pointer
```

The manifest records Git commit/tree IDs, each included file's SHA256, byte length and executable mode, every excluded tracked path with its reason, and the allowed shared links. Credential extensions, `.env*`, caches, environments, runtime/database paths and non-runtime binary formats are excluded. These filename rules are a safeguard, **not a secret detector**: review committed source before publication/deployment.

No symlinks or submodules from the committed source are packaged. The verifier rejects traversal/absolute paths, duplicate members, links, nonregular files, oversized archives, unexpected manifest entries and incorrect hashes. It verifies the complete archive before creating a staging directory. Extraction writes regular files directly; it never uses `tar.extractall`. Failed extraction is cleaned up, and no active pointer changes. A completed commit directory is never overlaid: a repeat staging request for an existing commit fails for inspection rather than merging files. Removed source files cannot survive into the next release directory.

## 1. Build and verify locally

Use a full commit SHA for a recorded release, or `HEAD` while preparing one. The helper resolves it once. Output should live under ignored `runtime/` or another artifact directory, not source control.

```bash
python3 scripts/release_artifact.py build --revision HEAD --output runtime/release.tar.gz
```

The command prints `commit`, `tree`, archive `sha256` and path. Use those **printed full values** below; `<COMMIT>` and `<SHA256>` are placeholders.

```bash
python3 scripts/release_artifact.py verify runtime/release.tar.gz --commit <COMMIT> --sha256 <SHA256>
```

The SHA256 verifies transfer integrity relative to the caller's recorded artifact. It is not a signature or an independent guarantee of trusted authorship. Keep the manifest/artifact hash with release evidence.

## 2. Upload and stage on Horde

After committing `scripts/release_artifact.py` and the candidate source/assets:

```bash
python3 scripts/deploy_horde.py --worker park-twin-rtx --revision <COMMIT>
```

The helper uses audited `hgx exec` calls, uploads binary-safe chunks into an incoming directory, checks the committed verifier's transfer SHA256, then runs that verifier against the archive's expected digest and commit. It stages a new `releases/<COMMIT>` directory and creates only the declared shared links. **The default does not update `current`, stop a service, copy the legacy database, install packages or restart anything.** An interrupted upload is not a release. A completed staged release can be reviewed before any activation.

For a local dry run of the exact same staging boundary:

```bash
python3 scripts/release_artifact.py stage runtime/release.tar.gz --root /tmp/park-release-review --commit <COMMIT> --sha256 <SHA256>
```

All managed root/shared/release parent paths must be real directories. Existing redirecting symlinks are rejected. Staged source should be treated as immutable; activation checks its exact regular-file and shared-link inventory, modes and hashes again.

## 3. Prepare runtime compatibility and activate deliberately

Before starting the first release, an operator must prepare `shared/.venv` with the project's documented backend/renderer requirements and a Python interpreter compatible with the installed native SDK/driver. Verify package versions and GPU availability. The empty `.venv` directory created during staging is only a reserved shared location; it is not a configured Python environment.

For migration from the legacy demo, stop its processes using its own recorded service commands, wait for complete exit and preserve its runtime/database as a backup. Copy the complete SQLite database only while the producer is stopped (including relevant WAL state, or use SQLite's backup API). Put the intended operational database under `shared/data`. Do not silently merge a running legacy source directory into a release. A release never contains the legacy environment, database or secrets.

Activation requires an explicit command:

```bash
python3 scripts/release_artifact.py activate --root /home/horde/park-twin-deploy --commit <COMMIT>
```

Alternatively, `deploy_horde.py --activate` performs the same source-pointer promotion after successful staging. Activation atomically replaces the `current` symlink; it **does not** change running processes. It refuses changed staged files, unexpected shared links and an existing real directory/file at `current`. Retain the previous release for rollback.

Service startup/shutdown must use a concrete resolved release directory, because the existing scripts derive their root from their own location. Stop the *old* release with its own `scripts/stop.py` while it is still identifiable, then start the new release with its `scripts/start.py` only after dependencies/data compatibility are checked. Runtime PID files are shared, so do not run two releases against that shared state simultaneously. Do not use a changed `current` pointer as evidence that the running process belongs to the new release. Existing start/stop PID identity and port behavior remain a separate process-control boundary to validate; this artifact change does not certify them.

Perform API health/data checks and actual GPU/browser acceptance for the new process. Capture deployed commit/tree, manifest/asset hashes, dependency versions, schema compatibility and evidence time with the results. The manifest identifies **staged source**; existing `/api` or renderer status endpoints do not automatically report it unless a separate runtime identity integration has been implemented.

## 4. Roll back source, then validate runtime

Stop the running candidate using its own release path. Inspect the prior release manifest and data-schema compatibility, activate the prior full commit with the same `activate` command, then start that concrete prior release and run its health/GPU acceptance checks. Activation rechecks the prior staged tree before promotion.

Source rollback preserves `shared/runtime`, `shared/data` and `shared/.venv`; it does not reverse database migrations or installed dependency changes. Backups/compatible schemas and environments are required before claiming operational rollback. No old release, shared data or incoming upload is automatically deleted by these scripts.

## CPU boundary checks

```bash
.venv/bin/python -m pytest -q tests/test_release_artifact.py
```

Tests use temporary local Git repositories and filesystems. They cover dirty worktree/index isolation, exclusion of runtime secrets, deleted files across fresh staging, persistence of shared state, explicit activation/rollback, archive/manifest corruption, unsafe paths/links and changed staged source. They do not contact Horde, restart native services or replace GPU acceptance evidence.
