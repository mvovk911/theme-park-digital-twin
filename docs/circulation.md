# Circulation audit and additive route preview

The existing scene does **not** yet support credible park-wide guest routing. Several visually nearby attractions have no connected pavement, queue rails block a wheel boarding shortcut, and a utility fence crosses a main promenade. This slice makes those defects visible before the planner is allowed to claim rerouting benefits.

`assets/circulation_graph.json` registers 26 nodes and 26 undirected edges to the existing, unchanged park. Twenty-two edges describe partial public circulation; two missing connections and two obstructed connections are excluded from every route. The graph uses the scene's meters and Z-up convention. Node Z = 0.30 m is a nominal route display datum; walking distances are plan distances, not a surveyed terrain profile.

`assets/circulation_overlay.usda` is an additive diagnostic layer. It authors only `/World/CirculationPreview`; it does not reference or edit the park, lights, cameras, materials, or ride geometry. Compose it alongside `park.usdc` for a preview. If creating a new composition root, explicitly author `upAxis = "Z"` and `metersPerUnit = 1` on that root; stage metadata must not be assumed to inherit from sublayers. Cyan solid lines are authored public paths, amber dashed lines are missing connections, red dashed lines are obstructions, and yellow markers identify entrances or approach points. Overlay lines float 0.38 m above their route datum to remain visible. Their 0.32 m drawing width has **no** relationship to path capacity or the assumed corridor width.

The baseline scene SHA-256 is `7e9f430e5302a9469e68fa649f2a1cbb0784bdf519a7a41421a96124b87a0c1c`. Both source hashes are also stored in the graph and checked against the files by tests. No baseline `.usda`, `.usdc`, or `.blend` asset was modified by this slice.

## What the audit found

| Connection | Existing geometry | Consequence |
|---|---|---|
| Main promenade → food plaza | Main promenade western edge is x = −5 m; dining plaza eastern edge is x = −11.5 m. There is 6.5 m of grass and a curb at x ≈ −5.1 m. | Food entrance is unreachable from the main graph. |
| Cross promenade → food plaza | Cross promenade southern edge is y = −11.5 m; dining plaza northern edge is y = −15.5 m. | The apparently adjacent food court also has a 4 m gap on its north side. |
| Cross promenade → coaster queue | Paving ends at y = −2.5 m. The queue gate is near (−18, −2), and a curb occupies y ≈ −2.4 m. | A public approach is reachable; the actual queue gate is not. A coaster-closure alternative begins at the public approach, not inside the unreachable queue. |
| Wheel queue approach → boarding | Queue rails run from x = 28 to 42 m at y = 10 and 12 m. | The graph reaches the public approach at (35, 8). It does not pretend to pass through rails or validate the boarding ramp. |
| East promenade → north promenade | The power-hub fence crosses y = 40 m from x = 46 to 69 m, across the east promenade. | The eastern north connection is blocked. Show access uses the west promenade. |
| Plaza centerline | Fountain basin radius is 3.7 m around (0, −7). | Routes go around the basin, with a genuine alternative if one side closes. |
| Promenade centerlines | Lamp posts stand at (0, −42), (±16, −7), (±54, −7), and (±62, 32), among others. | The authored lines offset around those known fixed obstructions. |
| Step-free continuity | Entry paving top is 0.35 m versus main promenade 0.24 m; central plaza top is 0.335 m. No connecting ramps are authored for these thresholds. | Entrance-to-wheel queries with `accessible_only=True` return unreachable. Local step-free labels are synthetic, not an accessibility certificate. |
| Lake boardwalk | The modeled deck and ramps do not establish a connection to the public paving network. | No invisible cross-lake shortcut is included. |

Source prims and dimensions are embedded in the graph: `/World/Park/LANDSCAPE/{MainPromenade,CrossPromenade,NorthernPromenade,WestPromenade,EastPromenade,WheelApproach,CentralPlaza,FountainBasin}`, `/World/Park/FOOD_COURT/DiningPlaza`, `/World/Park/ENTRY_GATE/EntryPaving`, and the corresponding queue, fence, and lamp source roots. `modeling/generate_park.py` and `modeling/detail_pass.py` supply the authored fence and curb endpoints. Tests compare paving dimensions against the actual committed USDA, not merely the generator's intent.

## Queries and measured model outputs

Run without USD, a database, GPU, or web service:

```bash
python modeling/circulation.py --from ENTRY_GATE --to RIDE_WHEEL
python modeling/circulation.py --from ENTRY_GATE --to SHOW_ARENA
python modeling/circulation.py --from ENTRY_GATE --to FOOD_COURT
python modeling/circulation.py --from coaster_approach --to RIDE_WHEEL
python modeling/circulation.py --from ENTRY_GATE --to RIDE_WHEEL --blocked-edge plaza_south_e
python modeling/circulation.py --from ENTRY_GATE --to RIDE_WHEEL --accessible
python modeling/circulation.py --write-overlay assets/circulation_overlay.usda
```

| Query | Distance in authored graph | Distance / assumed 1.2 m/s |
|---|---:|---:|
| Entrance → wheel **public approach** | 94.124 m | 78.44 s |
| Same, with `plaza_south_e` closed | 124.012 m | 103.34 s |
| Entrance → show west-side approach | 201.981 m | 168.32 s |
| Coaster **public approach** → wheel public approach | 73.314 m | 61.09 s |
| Entrance → food entrance | Unreachable | Not reported |
| Entrance → coaster boarding gate | Unreachable | Not reported |
| Entrance → wheel with authored step-free filter | Unreachable | Not reported |

These are inspectable geometric calculations, **not** calibrated walking predictions. They exclude dwell time, queues, crowd interaction, density, guest mobility differences, preferences, weather, and signage compliance. There is no path-capacity, evacuation, ride-boarding, or safety model. A reachable approach does not mean an operating attraction has spare capacity. Neither the scenario planner nor renderer is wired to this graph yet.

The pure `find_route` function accepts graph node IDs or the five explicitly mapped asset IDs, a list of blocked edge IDs, `accessible_only`, and a positive finite walking-speed assumption. Unknown nodes or closure IDs raise errors instead of silently ignoring them. Excluded graph connections are never enabled by ordinary route queries. Results retain synthetic/unvalidated labels, source-scene hash, origin/destination scope, node and edge IDs, and the assumptions used. Queries never mutate the authored graph.

## Proposed physical design scenario — not applied

Preserve this diagnostic baseline and create a separate design variant before changing geometry or declaring an operational benefit:

1. **Connect dining first.** Test a roughly 12 × 2 m connector centered near (−8.25, −26.5), overlapping the main promenade and dining plaza. Open the matching curb segment. Keep clear of the bins near (−12, −28), chairs, and menu fixtures; verify their complete bounds rather than assuming the first sketch is clear. Grade the 0.085 m surface-height difference explicitly. This is a useful isolated experiment: a previously unreachable destination becomes reachable with a known walking cost.
2. **Complete the coaster approach.** Add a short paved throat from the cross promenade to the queue gate, opening the curb near y = −2.4. Determine the usable gate opening and the queue's actual inlet before choosing its width. The current queue rail drawing is insufficient to prove a valid boarding path.
3. **Redesign the wheel queue inlet.** Model explicit entrance gates or a connected perimeter bypass around the y = 10 and 12 rails. Avoid merely deleting rails without replacing the queue layout. Verify the ramp and platform elevations, rail clearances, and boarding interface separately.
4. **Separate guests from utilities.** Reroute public access or redraw the power-hub perimeter so the east/north public connection is continuous and the utility compound remains separated. A gap in a utility fence alone is not an adequate guest-route design.
5. **Resolve thresholds.** Add explicit transitions at the entrance and central plaza before claiming step-free continuity. Update the graph's accessibility labels only after those modeled surfaces and clearances are inspected.

For every variant: preserve baseline hashes, export a separate layer/scene, recompute route reachability and lengths, inspect native OVRTX views, and compare against the diagnostic baseline. Only after those checks should the planning engine use walking delay or route availability as a decision constraint. Width-based crowd capacity needs a separately calibrated pedestrian model; multiplying width by an arbitrary throughput constant would invent evidence.

## Validation performed

- 21 pure CPU tests pass: source hashes and dimensions, real detours, missing-route abstention, forbidden fountain/grass shortcuts, closure handling, speed sensitivity, accessibility filtering, invalid inputs, immutability, and deterministic overlay output.
- Additional USD 26.8 inspection opens the additive layer successfully, verifies its curve widths, resolves all nine registered paving prims and twelve obstacle source prims in the actual USDC, and matches eight rectangular footprints to their USD world bounds.
- An anonymous composition containing the baseline and preview also opens successfully when the composition root explicitly authors Z-up and meters.
- The diagnostic overlay was rendered with actual OVStage 0.3.0 and OVRTX 0.6.0 on the Horde L40 at 20:21:56–20:22:02 UTC. Both captured views completed native cleanup without errors. [Capture report](images/fox-cycle-20261019/circulation-baseline/report.json) binds the exact scene, graph, overlay, script and image hashes. This is a separate static design review, not live telemetry or integration into the application.

The centerline check samples at intervals no greater than 0.1 m. It checks registered paving plus selected known obstacle footprints. It is deliberately not an obstacle-complete navmesh, does not validate the full assumed 2 m corridor envelope, and excludes dynamic guest meshes. Source-scene hash checks force re-review when the baseline asset changes.

## Native design review

![Actual OVRTX plan view of the unchanged park and diagnostic circulation layer](images/fox-cycle-20261019/circulation-baseline/plan-view.png)

[Perspective view](images/fox-cycle-20261019/circulation-baseline/overview.png).
Cyan paths are the partial authored graph; amber/red dashed links remain excluded.
The native capture script is `scripts/render_circulation.py --output <directory>`
and requires the GPU Python environment with OVStage/OVRTX. A cold shader startup
exceeded an initial 120-second control-plane timeout. A subsequent root-layer
syntax error was corrected and checked with a USD parser before the successful
5.833-second capture using the warmed cache. Runtime APIs and the live renderer
were not modified by the static capture.
