# Theme Park Digital Twin — Project Concept & Pilot Plan

A 10-page, landscape PDF slide deck illustrating a connected theme-park digital twin, its API ecosystem, operational value, visualization and proposed pilot.

## Deliverables

- `../project-concept.pdf` — presentation PDF, with selectable text, vector illustrations and clickable references.
- `build_deck.py` — editable source for content and vector artwork.
- `sources.md` — research links and attribution notes.

## Reproduce

Requires Python 3 and the DejaVu Sans regular/bold TTF files. The script uses `/usr/share/fonts/truetype/dejavu/`; change that path for another OS.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build_deck.py
```

Run the commands from this `docs/deck-source` directory. The generated PDF replaces `docs/project-concept.pdf`. Pass `--output /tmp/project-concept.pdf` to validate without replacing the published artifact. The generator uses invariant PDF metadata for deterministic repeat builds; the original delivered PDF has older creation metadata, so its binary hash differs even when page content matches. Optional preview and document checks can be performed with PyMuPDF. Preview images are reproducible and excluded from the repository.

## Assumptions and limits

- Original vector illustrations and an illustrative interface; no real park geometry or operational data.
- Architecture and product direction are proposals based on the referenced material.
- API availability, licensing, latency and permissions require vendor-specific discovery.
- The 12-week pilot is an indicative planning sequence, conditional on data access and team availability.
- Benefits are measurement hypotheses; the deck makes no quantified ROI claim.
- Forecasts need park-specific calibration. Ride safety functions remain in dedicated local control systems.

## Validation

The PDF was rendered and visually inspected. It contains ten 16:9 pages, selectable text, and eight clickable reference regions. Text layout and page bounds were checked. Original artwork requires no external image downloads.
