# Final FOX-inspired review deck

[Five-page final PDF](../../fox-review-final.pdf) · [Cover preview](../../images/fox-cycle-20261019/review-deck-final-cover.png) · [Completed v2 run contract](../../experiments/run-analysis/final/review-run.json)

This artifact uses the publicly published source/evidence checkpoint `cbe1b5c1d4857eae45aadc2325b86957237581c9`. The original concept PDF, interim review PDF and [editable editorial source](../fox-review.md) remain unchanged.

The deck preserves separate evidence scopes: the FOX-inspired architecture; actual six-check GPU incident walkthrough on `afa84a1`; matched native dining renders and partial authored graph; independent 324-case policy accounting; and the final two-track sampled run. The older 407 local/40 browser counts remain labeled as that checkpoint, rather than being presented as a new final combined qualification.

## Reproduce

Use the separate document tooling environment, with the committed pinned dependencies:

```bash
python3 -m venv /tmp/park-review-tools
/tmp/park-review-tools/bin/pip install -r docs/deck-source/requirements-fox-review.txt
/tmp/park-review-tools/bin/python scripts/build_fox_review_deck.py \
  --source-revision cbe1b5c1d4857eae45aadc2325b86957237581c9 \
  --run-summary docs/experiments/run-analysis/final/review-run.json \
  --output docs/fox-review-final.pdf
```

Run from the repository checkout with the input hashes recorded in [fox-review-final.manifest.json](fox-review-final.manifest.json). The generator uses the shared v2 validator in `operators/analyze_fox_run.py`; it will not substitute an eight-hour clock for reconciled schedule coverage and verified source evidence. Its PDF metadata is deterministic, and a second build with the same inputs/options produced identical PDF bytes.

The generator initially creates the manifest, layout-validation JSON and five PNG previews beside the PDF. Publication packaging moves those JSON files into this directory, copies page 1 to `docs/images/fox-cycle-20261019/review-deck-final-cover.png`, and retains all page previews under ignored `runtime/fox-cycle-20261019/review-deck/final-pinned/`. No application dependencies, scene geometry or source documents are changed by this packaging.

## Retained run qualifications

- Fixed-source API track: 96 functional cycles, no failed checks; 300-second cadence; 19.438 seconds total uncovered schedule time, maximum interval 0.591 seconds; one observed deployment.
- GPU observation track: 960 samples, **one failed sample retained**; 30-second cadence; 8.692 seconds total uncovered schedule time, maximum interval 0.010 seconds; four observed deployments.
- Both elapsed windows reach eight hours. No recorded health-only pauses occurred. Source identities were verified; the full transition and interval records remain in the run contract and PDF manifest.
- These are sampled schedule windows with a declared two-second tolerance. They do not establish continuous uptime, eight hours of uninterrupted functional activity, an uninterrupted single-release soak, physical operational safety or real-world business value. GPU observation request duration was not retained and is not invented.

The badge therefore reads **8H SAMPLED REVIEW**. Failed records, gaps, changing deployments and model limitations remain visible.

## Artifact acceptance

All five final pages were visually inspected. [Layout validation](fox-review-final.validation.json) records five pages, 154 selectable text spans within page bounds and 12 clickable source links. [Publication checks](publication-check.json) verify that all 11 repository footer targets exist at the pinned checkpoint; the remaining link is NVIDIA's primary FOX announcement. Text assertions check that the final page retains the actual counts, failure, gaps, multiple deployments and continuous-uptime qualification.

PDF SHA256:

```text
0aa2fb4fa784a0d83062a2b9d4db71849f4c83e66e212ce71be9de9e0f49c088
```

Input run-contract SHA256:

```text
21502115dec37330d0751d3435ca451385ce8bec54d8f9cc2ea37fbd25d456ae
```

The interim review PDF remains byte-identical at SHA256 `86872c0df21364b48ad2e0508ed9ade59b554d752e12ec764901660af19061ec`.
