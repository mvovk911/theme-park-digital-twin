# Five-minute operator walkthrough

All values and actions in this application are synthetic. The 3D viewport is
rendered by OVRTX on the GPU, with scene state held by OVStage.

1. **Orient:** open the console, wait for the renderer's first frame, orbit by
   dragging and zoom with the mouse wheel. The Home control restores the park view.
   Trees, fencing, water and paths form context around two animated rides and ten
   service assets.
2. **Identify:** click a building or ride surface in the rendered image. A native
   GPU pick returns a USD prim path, mapped through the registry to a SQLite asset.
   Inspect status, history, dependencies, staffing and maintenance. Labels and the
   asset list provide alternative ways to select; Locate moves the camera closer.
3. **Compare first:** choose Ride closure and open its comparison. Before/after
   values use the same simulation tick. Read the assumptions and note that the live
   scenario has not changed. Apply it to demonstrate a disruption.
4. **Respond:** the coaster stops, its status closes, and the operational brief
   changes. Select the coaster, dispatch maintenance and inspect the work order and
   audit trail. Try guest rerouting. These change only the synthetic services.
5. **Explore dependencies:** apply Power fault or Water leak. Switch to the Energy
   overlay; inspect the utility asset and its dependents. Repair the simulated leak
   and watch the flow metric recover. The water metric includes circulation and is
   not a measure of net water consumption.
6. **Inspect the backbone:** open a source-system card to see the exact synthetic
   payload and intended API boundary. The architecture dialog explains how these
   independent feeds join asset context and the spatial stage.
7. **Reset:** apply Normal and reset the demo actions, then return Home. The audit
   trail preserves operator actions for review.

The scenario lab is a heuristic comparison, not a calibrated forecast. Queue
averages exclude closed attractions, so a lower average alone can conceal reduced
capacity. Assess open rides, throughput, alerts and individual queues together.

The current console shares one camera and one simulator across all viewers. A
production service needs session isolation, access control, source quality rules,
replay, durable workflow acknowledgements and operational monitoring.
