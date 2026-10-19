# Dining connection: a separate, testable design scenario

The baseline food plaza is unreachable in the authored circulation graph. This experiment adds one graded connector and opens one curb, allowing an operator to compare an explicit physical design with the unchanged diagnostic baseline. It does not change the running app or claim that the park has been built this way.

The new route reaches a **plaza entrance**, not restaurant service counters or an interior path through tables and chairs. Its modeled plan distance from the park entrance is **40.852 m**, or **34.04 seconds at an assumed 1.2 m/s**. Closing the new connector makes that destination unreachable again. A step-free route from the park entrance still cannot be asserted because the separate entry threshold remains unresolved.

## Exact geometry

| Component | Authored design |
|---|---|
| Connector footprint | x = −13.5…−4.5 m, y = −27.4…−25.4 m; 9 × 2 m |
| Food-side landing | x = −13.5…−11.5 m, top z = 0.325 m, matching the dining plaza |
| Graded portion | x = −11.5…−5.0 m; top changes continuously from z = 0.325 to 0.240 m |
| Geometric grade | 0.085 / 6.5 = 1.3077% along the modeled slope |
| Main-side landing | x = −5.0…−4.5 m, top z = 0.240 m, matching the main promenade |
| Curb opening | y = −27.4…−25.4 m at the original curb x ≈ −5.1 m |
| New entrance point | (−12.5, −26.4), 0.6 m north of the baseline food entrance |

The sloped mesh has flat overlapping landings on both existing paved surfaces. It models the actual 0.085 m height difference; it is not a flat bridge that introduces a step at either end. The graph continues to calculate **2D plan distance** on its nominal z = 0.30 m display datum. It does not pretend to integrate a measured terrain profile. The grade's surface-length difference is negligible for this demonstration, but the distinction remains explicit in the graph and evidence.

The stronger layer deactivates only `/World/Park/LANDSCAPE/PathCurb`. Its original bounds were checked directly in the USDC: x = −5.21…−4.99 m, y = −46.5…−19.5 m, z = 0.135…0.385 m. Replacement south and north segments preserve its original width, height, position, and `/World/Materials/cream` material, while leaving the new opening. Paving uses `/World/Materials/path`.

All additions are under `/World/Park/DINING_CONNECTION_DESIGN`. The base park USDA, USDC, Blender file, and circulation graph remain byte-for-byte unchanged. Their hashes, the variant layer hash, and the variant graph hash are captured in the evidence JSON.

## Full-footprint obstacle inspection

The builder opens the actual baseline USD and the composed variant, then checks **the entire 9 × 2 m paving rectangle**, with a conservative vertical prism z = 0.24…2.425 m. It uses world-aligned bounds of nearby low geometry, including bins, lids, tables, chairs, menu boards, curbs, and synthetic guest meshes. It does not merely test the route centerline.

The composed audit records 27 nearby fixed obstacle primitives, 30 guest primitives, four support surfaces, and one paving-joint decal. It finds no positive-volume intersection between the full connector prism and fixed obstacles or the current guest meshes. The replacement curbs touch the paving boundary by design and do not intrude into its footprint.

Selected measured gaps from the *paving boundary* to conservative object bounds:

| Nearby primitive | Geometric gap |
|---|---:|
| Bin lids south of the connector | 0.240 m |
| Nearby table | 0.361 m diagonally; its y-bound is 0.200 m beyond the connector's northern edge |
| Nearest chair | 1.100 m |
| Nearest current guest primitive | 0.372 m |

These gaps are **not a clearance-safety or crowd-capacity claim**. They show that this precise synthetic footprint does not intersect the inspected source geometry. Practical passing space, edge protection, guest behavior, maintenance access, furniture movement, field tolerances, and local requirements need separate validation. The source scene is illustrative, not surveyed. Ground/support surfaces and paving-joint markings are identified explicitly rather than silently counted as obstructions or omitted from the evidence.

The baseline entrance point at (−12.5, −27) was too close to the bins for this full 2 m footprint. The variant maps `FOOD_COURT` to the new landing point at (−12.5, −26.4); it preserves the old node and explains the adjustment in its provenance. It adds no route through the restaurant interior.

## Files and reproduction

- [`dining_connection.usda`](../assets/variants/dining_connection.usda): stronger geometry layer, with the single curb override and new paving/curb segments.
- [`dining_circulation_graph.json`](../assets/variants/dining_circulation_graph.json): separate graph bound to the baseline graph and variant-layer hashes.
- [`dining_connection_evidence.json`](../assets/variants/dining_connection_evidence.json): actual source/composed bounds, complete nearby-object audit, before/after/closure/accessibility query results, and limitations.
- [`modeling/dining_variant.py`](../modeling/dining_variant.py): deterministic layer/graph authoring and USD inspection.
- [`tests/test_dining_variant.py`](../tests/test_dining_variant.py): 11 acceptance tests; together with the baseline circulation tests, **32 tests pass**.

Build using an environment with `usd-core` installed:

```bash
python modeling/dining_variant.py
python -m pytest tests/test_dining_variant.py tests/test_circulation.py -q
python modeling/circulation.py --graph assets/variants/dining_circulation_graph.json --from ENTRY_GATE --to FOOD_COURT
python modeling/circulation.py --graph assets/variants/dining_circulation_graph.json --from ENTRY_GATE --to FOOD_COURT --blocked-edge dining_connector_link
python modeling/circulation.py --graph assets/variants/dining_circulation_graph.json --from ENTRY_GATE --to FOOD_COURT --accessible
```

To view the design, compose `dining_connection.usda` **stronger than** `park.usdc`. A newly created composition root must explicitly author Z-up and meters. Do not bake the variant into the baseline to demonstrate it; retaining both states is what makes the comparison reviewable.

CPU/USD checks open the composed stage, verify the overridden curb, confirm actual paving points against the grade profile, inspect material bindings, and audit the full footprint. **Native OVRTX screenshots are still an integration step.** The saved CPU evidence says `native_gpu_rendered: false`; it does not substitute for a GPU render or a live operational test.

## Value and remaining limits

This is a small example of a useful spatial constraint: an agent should reject a rerouting recommendation when its proposed destination has no connected guest path. A separate physical design can then change that constraint, with auditable distance, grade, objects affected, and closure behavior. It is more informative than changing a queue number while ignoring whether guests can get there.

No business benefit is proven here. The new connection may affect demand distribution, walking effort, queues, accessibility, and service access; those effects require further models and real measurements. This experiment establishes only a geometrically inspectable connection and honest before/after reachability.

## Native visual evidence

The [matched L40/OVRTX comparison](circulation-native-rendering.md#actual-native-comparison)
shows the unchanged baseline and separate proposed connector with identical
camera settings. These are actual native renders of the authored layers, not
concept illustrations or proof of guest throughput.
