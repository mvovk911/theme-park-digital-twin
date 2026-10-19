#!/usr/bin/env python3
"""Small, synthetic circulation graph; independent of USD and runtime services.

The JSON is the authored source. This module validates it, answers shortest-path
queries, and emits an additive USD preview. It never edits the baseline park.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = ROOT / "assets/circulation_graph.json"


def load_graph(path: Path = DEFAULT_GRAPH) -> dict:
    graph = json.loads(Path(path).read_text())
    validate_graph(graph)
    return graph


def distance(a: list, b: list) -> float:
    return math.dist(a, b)


def _inside(point: list, surface: dict) -> bool:
    x, y = point[:2]
    if surface["shape"] == "rectangle":
        xmin, ymin, xmax, ymax = surface["bounds_xy_m"]
        return xmin - 1e-6 <= x <= xmax + 1e-6 and ymin - 1e-6 <= y <= ymax + 1e-6
    return math.dist((x, y), surface["center_xy_m"]) <= surface["radius_m"] + 1e-6


def validate_graph(graph: dict) -> None:
    """Check references, dimensions, and full walkable centerlines against paving.

    This is geometry registration, not collision-free navmesh certification.
    Excluded edges explicitly encode known defects and need not be on paving.
    """
    if graph.get("units") != "meters" or graph.get("up_axis") != "Z":
        raise ValueError("Graph must use meters and Z-up")
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}
    surfaces = {s["id"]: s for s in graph["surfaces"]}
    if len(nodes) != len(graph["nodes"]) or len(edges) != len(graph["edges"]):
        raise ValueError("Duplicate graph identifier")
    for node in nodes.values():
        if len(node["position_m"]) != 3 or not all(math.isfinite(v) for v in node["position_m"]):
            raise ValueError("Invalid node coordinates")
    for edge in edges.values():
        if edge["from"] not in nodes or edge["to"] not in nodes or edge["from"] == edge["to"]:
            raise ValueError("Invalid edge endpoints")
        if edge["status"] not in ("walkable", "missing_connection", "obstructed"):
            raise ValueError("Unknown edge status")
        if not math.isfinite(edge["assumed_corridor_width_m"]) or edge["assumed_corridor_width_m"] <= 0:
            raise ValueError("Invalid authored width")
        if not isinstance(edge["modeled_step_free"], bool):
            raise ValueError("Step-free label must be explicit boolean")
        if edge["status"] != "walkable":
            if not edge.get("reason"):
                raise ValueError("Excluded edges require a reason")
            continue
        a, b = nodes[edge["from"]]["position_m"], nodes[edge["to"]]["position_m"]
        if distance(a, b) <= 0:
            raise ValueError("Zero length walkable edge")
        cited = [surfaces[s] for s in edge["surface_ids"]]
        for step in range(max(2, math.ceil(distance(a, b) / 0.1)) + 1):
            count = max(2, math.ceil(distance(a, b) / 0.1))
            point = [a[i] + (b[i] - a[i]) * step / count for i in range(3)]
            if not any(_inside(point, s) for s in cited):
                raise ValueError(f"Edge {edge['id']} leaves its cited paving")
            for obstacle in graph["excluded_ground_footprints"]:
                if _inside(point, obstacle):
                    raise ValueError(f"Edge {edge['id']} crosses {obstacle['id']}")
    for asset, node in graph["asset_entrances"].items():
        if node not in nodes:
            raise ValueError(f"Unknown entrance for {asset}")


def find_route(graph: dict, origin: str, destination: str, *, blocked_edges=(),
               accessible_only: bool = False, walking_speed_mps: float = 1.2) -> dict:
    """Dijkstra on authored paths. Asset IDs resolve to explicit entrance points.

    accessible_only means the authored step-free labels, never an accessibility
    certification. No travel-time prediction or crowd capacity is inferred.
    """
    validate_graph(graph)
    if isinstance(walking_speed_mps, bool) or not math.isfinite(walking_speed_mps) or walking_speed_mps <= 0:
        raise ValueError("Walking speed must be finite and positive")
    nodes = {n["id"]: n for n in graph["nodes"]}
    all_edges = {e["id"]: e for e in graph["edges"]}
    blocked = set(blocked_edges)
    if blocked - all_edges.keys():
        raise ValueError("Unknown blocked edge: " + ", ".join(sorted(blocked - all_edges.keys())))
    start = graph["asset_entrances"].get(origin, origin)
    end = graph["asset_entrances"].get(destination, destination)
    if start not in nodes or end not in nodes:
        raise ValueError("Unknown origin or destination")
    adjacency = {n: [] for n in nodes}
    for edge in all_edges.values():
        if edge["status"] != "walkable" or edge["id"] in blocked:
            continue
        if accessible_only and not edge["modeled_step_free"]:
            continue
        a, b = edge["from"], edge["to"]
        length = distance(nodes[a]["position_m"], nodes[b]["position_m"])
        adjacency[a].append((b, length, edge["id"]))
        adjacency[b].append((a, length, edge["id"]))
    best = {start: 0.0}
    queue = [(0.0, start, [], [start])]
    result = {
        "synthetic": True, "calibrated": False,
        "graph_version": graph["version"], "source_scene_sha256": graph["source_scene_sha256"],
        "origin": origin, "destination": destination, "origin_node": start, "destination_node": end,
        "destination_note": nodes[end].get("note", ""),
        "entrance_scope_note": graph.get("entrance_scope_notes", {}).get(destination, ""),
        "blocked_edges": sorted(blocked), "accessible_only": accessible_only,
        "accessibility_basis": "authored step-free labels; not certified",
        "walking_speed_mps": walking_speed_mps,
        "limitations": ["Partial authored graph, not an obstacle-complete navmesh",
                        "Distance / assumed speed excludes queues, stops, density, and guest mobility variability",
                        "No capacity, evacuation, boarding, or accessibility certification"],
    }
    while queue:
        length, current, route_edges, route_nodes = heapq.heappop(queue)
        if length > best[current]:
            continue
        if current == end:
            return {**result, "reachable": True, "distance_m": round(length, 3),
                    "assumed_walking_seconds": round(length / walking_speed_mps, 2),
                    "node_ids": route_nodes, "edge_ids": route_edges,
                    "positions_m": [nodes[n]["position_m"] for n in route_nodes],
                    "minimum_authored_corridor_width_m": min((all_edges[e]["assumed_corridor_width_m"] for e in route_edges), default=None)}
        for following, cost, edge_id in adjacency[current]:
            candidate = length + cost
            if candidate < best.get(following, math.inf):
                best[following] = candidate
                heapq.heappush(queue, (candidate, following, route_edges + [edge_id], route_nodes + [following]))
    return {**result, "reachable": False, "distance_m": None, "assumed_walking_seconds": None,
            "node_ids": [], "edge_ids": [], "positions_m": [],
            "reason": "No route in the authored graph under these closures and accessibility labels",
            "destination_note": nodes[end].get("note", "")}


def write_overlay(graph: dict, destination: Path) -> None:
    """Standalone layer at /World/CirculationPreview; no baseline references.

    Curves float above paving for visibility. Red/amber lines are excluded graph
    links, not paved routes. Prefix and edge custom attributes support picking.
    """
    validate_graph(graph)
    nodes = {n["id"]: n for n in graph["nodes"]}
    lines = ['#usda 1.0', '(', '    defaultPrim = "World"', '    metersPerUnit = 1', '    upAxis = "Z"', ')', '',
             'def Xform "World" {', '    def Xform "CirculationPreview" {',
             '        custom string park:overlayKind = "synthetic_circulation_preview"',
             '        custom string park:disclaimer = "Cyan: authored paving; amber: missing connection; red: obstruction. Not certified navigation."']
    for edge in graph["edges"]:
        color = {"walkable": (0.05, 0.85, 1), "missing_connection": (1, 0.6, 0.04), "obstructed": (1, 0.08, 0.12)}[edge["status"]]
        a, b = [nodes[edge[k]]["position_m"] for k in ("from", "to")]
        # Nonwalkable links use separated dashes, never a continuous apparent path.
        segments = [(a, b)] if edge["status"] == "walkable" else [
            ([a[j] + (b[j] - a[j]) * i / 12 for j in range(3)],
             [a[j] + (b[j] - a[j]) * (i + .5) / 12 for j in range(3)]) for i in range(12)]
        for index, (p, q) in enumerate(segments):
            points = ", ".join(f"({v[0]:.5f}, {v[1]:.5f}, {v[2] + .38:.5f})" for v in (p, q))
            lines += [f'        def BasisCurves "{edge["id"]}_{index:02d}" {{',
                      '            uniform token type = "linear"', '            uniform token wrap = "nonperiodic"',
                      '            int[] curveVertexCounts = [2]', f'            point3f[] points = [{points}]',
                      '            float[] widths = [0.32] ( interpolation = "constant" )',
                      f'            color3f[] primvars:displayColor = [{color}]',
                      f'            custom string park:edgeId = "{edge["id"]}"',
                      f'            custom string park:routeStatus = "{edge["status"]}"', '        }']
    for node in graph["nodes"]:
        if node["kind"] not in ("entrance", "approach"):
            continue
        x, y, z = node["position_m"]
        lines += [f'        def Sphere "{node["id"]}" {{', '            double radius = 0.55',
                  f'            double3 xformOp:translate = ({x}, {y}, {z + .65})',
                  '            uniform token[] xformOpOrder = ["xformOp:translate"]',
                  '            color3f[] primvars:displayColor = [(1, 0.85, 0.2)]',
                  f'            custom string park:nodeId = "{node["id"]}"', '        }']
    lines += ['    }', '}', '']
    destination.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--from", dest="origin", default="ENTRY_GATE")
    parser.add_argument("--to", dest="destination", default="RIDE_WHEEL")
    parser.add_argument("--blocked-edge", action="append", default=[])
    parser.add_argument("--accessible", action="store_true")
    parser.add_argument("--speed", type=float, default=1.2)
    parser.add_argument("--write-overlay", type=Path)
    args = parser.parse_args()
    graph = load_graph(args.graph)
    if args.write_overlay:
        write_overlay(graph, args.write_overlay)
    print(json.dumps(find_route(graph, args.origin, args.destination,
                               blocked_edges=args.blocked_edge, accessible_only=args.accessible,
                               walking_speed_mps=args.speed), indent=2))


if __name__ == "__main__":
    main()
