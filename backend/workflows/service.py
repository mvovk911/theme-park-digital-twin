"""One bounded action: synthetic maintenance dispatch with fresh preconditions."""
from datetime import datetime, timedelta
import json
from uuid import uuid4
from backend.planning.evidence import verify_bundle
from .contracts import WorkflowError

TARGETS = ["RIDE_COASTER", "RIDE_WHEEL", "POWER_HUB", "WATER_PLANT"]
REQUIRED_FIELDS = ["status", "maintenance.inspection_status", "maintenance.open_work_orders"]


def capabilities():
    return {"synthetic": True, "physical_control": False,
            "supported_actions": [{"action": "dispatch_maintenance", "asset_ids": TARGETS, "at_minute": 0,
                                   "outcome": "accepted_workflow_not_repair"}],
            "unsupported_actions": {action: "No bounded execution contract is implemented for this action" for action in ["reroute_guests", "add_staff", "shed_load", "repair_leak", "replenish_stock", "reset"]},
            "proposal_ttl_seconds": {"min": 30, "max": 300, "default": 120},
            "required_fresh_fields": REQUIRED_FIELDS,
            "evidence_is_authority": False,
            "authorization": "Explicit synthetic-only API invocation plus independently checked current preconditions; no real-system authorization."}


class WorkflowService:
    """Call under the app's view lock, then connector lock, then park lock.

    The final store lock serializes local proposal intent/completion. Existing
    ParkSimulator receipts bridge a crash between the two SQLite transactions.
    This is a single-gateway synthetic workflow, not a distributed transaction.
    """
    def __init__(self, park, read_model, connectors, evidence, store):
        self.park, self.read_model, self.connectors = park, read_model, connectors
        self.evidence, self.store = evidence, store

    def _current(self, target):
        state = self.read_model.snapshot()
        if state.get("synthetic") is not True or target not in TARGETS:
            raise WorkflowError("unsupported_workflow_target", "Only supported synthetic CMMS assets may receive this workflow", 422)
        asset = next((a for a in state["assets"] if a["id"] == target), None)
        if asset is None:
            raise WorkflowError("workflow_asset_missing", "Current asset is unavailable")
        now = self.connectors.clock()
        fields = asset.get("data_quality", {}).get("fields", {})
        for metric in REQUIRED_FIELDS:
            field = fields.get(metric, {})
            try:
                age = (now - datetime.fromisoformat(field["source_timestamp"].replace("Z", "+00:00"))).total_seconds()
                fresh = 0 <= age <= field["stale_after_seconds"]
            except (ValueError, TypeError, KeyError):
                fresh = False
            source_id = field.get("source_id")
            source_known_synthetic = source_id in self.connectors.adapters and self.connectors.adapters[source_id].synthetic is True
            if field.get("status") != "good" or field.get("synthetic") is not True or not source_known_synthetic or not fresh:
                raise WorkflowError("workflow_input_not_fresh", f"Fresh authoritative synthetic observation required: {metric}")
        orders = [dict(row) for row in self.park.db.execute("SELECT * FROM work_orders WHERE asset_id=? AND status='open' ORDER BY id", (target,))]
        observed_count = asset["maintenance"]["open_work_orders"]
        if observed_count != len(orders):
            raise WorkflowError("workflow_source_disagreement", "CMMS observation and synthetic work-order store disagree")
        condition = {"scenario": state["scenario"], "asset_id": target, "status": asset["status"],
                     "asset_type": asset["type"], "field_sources": {metric: fields[metric]["source_id"] for metric in REQUIRED_FIELDS},
                     "inspection_status": asset["maintenance"]["inspection_status"],
                     "observed_open_work_orders": observed_count, "open_work_order_ids": [o["id"] for o in orders]}
        return state, asset, condition

    def create(self, request):
        with self.store.lock:
            payload = request.model_dump()
            existing = self.store.by_request(request.request_id, payload)
            if existing:
                return {"proposal": existing, "idempotency": {"replayed": True}}
            bundle = self.evidence.get(request.bundle_id)
            verify_bundle(bundle)
            plan = bundle["payload"]
            branch = next((b for b in plan["result"]["branches"] if b["id"] == request.branch_id), None)
            if branch is None or request.action_index >= len(branch["action_schedule"]):
                raise WorkflowError("proposal_action_missing", "Selected saved comparison action does not exist", 422)
            action = branch["action_schedule"][request.action_index]
            if action["action"] != "dispatch_maintenance" or action["at_minute"] != 0:
                raise WorkflowError("unsupported_workflow_action", "Only immediate synthetic maintenance dispatch is supported", 422)
            state, asset, condition = self._current(action["asset_id"])
            if plan["request"]["scenario"] != state["scenario"]:
                raise WorkflowError("hypothetical_scenario_not_active", "A hypothetical saved scenario cannot authorize action on the current park")
            if condition["open_work_order_ids"]:
                raise WorkflowError("work_order_already_open", "A current work order already covers this asset; inspect that order instead of creating another proposal",
                                    context=self._conflict_context(condition))
            if asset["status"] != "fault" and asset["maintenance"]["inspection_status"] == "passed":
                raise WorkflowError("no_current_maintenance_need", "Current asset has neither a fault nor an inspection issue; closure alone is not a maintenance diagnosis")
            now = self.connectors.clock()
            ident = uuid4().hex
            proposal = {"id": ident, "status": "proposed", "synthetic": True, "physical_effect": False,
                        "created_at": now.isoformat(), "expires_at": (now + timedelta(seconds=request.ttl_seconds)).isoformat(),
                        "action": {"action": "dispatch_maintenance", "asset_id": action["asset_id"]},
                        "evidence_refs": {"bundle_id": request.bundle_id, "branch_id": request.branch_id, "action_index": request.action_index,
                                          "plan_id": plan["result"]["plan_id"], "historical_evidence_is_authority": False},
                        "preconditions": condition, "creation_state_revision": state["accepted_state_revision"],
                        "create_request_id": request.request_id, "execution_request_id": None,
                        "command_request_id": "proposal:" + ident,
                        "execution_scope": "synthetic_dispatch_only", "receipt": None, "readback": None}
            self.store.create(proposal, request.request_id, payload)
            return {"proposal": proposal, "idempotency": {"replayed": False}}

    @staticmethod
    def _conflict_context(condition, previous=None):
        """Return an inspectable next step when stale approval cannot proceed."""
        current_orders = condition["open_work_order_ids"]
        return {"asset_id": condition["asset_id"],
                "asset_detail_url": "/api/assets/" + condition["asset_id"],
                "current_work_order_ids": current_orders,
                "next_step": "inspect_existing_work_order" if current_orders else "review_current_conditions_then_create_proposal",
                "changed_fields": {key: {"proposed": previous.get(key), "current": value}
                                   for key, value in condition.items()
                                   if previous is not None and previous.get(key) != value}}

    def _existing_receipt(self, proposal):
        row = self.park.db.execute("SELECT payload,acknowledgement FROM action_receipts WHERE request_id=?", (proposal["command_request_id"],)).fetchone()
        if row:
            if json.loads(row["payload"]) != proposal["action"]:
                raise WorkflowError("command_receipt_conflict", "Stored command receipt does not match this proposal")
            return json.loads(row["acknowledgement"])
        return None

    def _complete(self, proposal, receipt, recovered):
        row = self.park.db.execute("SELECT * FROM work_orders WHERE id=? AND asset_id=?", (receipt.get("work_order_id"), proposal["action"]["asset_id"])).fetchone()
        if row is None:
            raise WorkflowError("work_order_readback_missing", "Command was acknowledged but its work order cannot be verified; retry with the same request ID")
        state = self.read_model.snapshot()
        asset = next(a for a in state["assets"] if a["id"] == proposal["action"]["asset_id"])
        status_field = asset.get("data_quality", {}).get("fields", {}).get("status", {})
        status_evidence = {"value": asset["status"], "quality": status_field.get("status", "unknown"),
                           **{key: status_field.get(key) for key in ("source_id", "source_timestamp", "synthetic", "stale_after_seconds")}}
        proposal.update(status="accepted_workflow_not_repair", receipt=receipt,
                        readback={"work_order": dict(row), "observed_at": self.connectors.clock().isoformat(),
                                  "asset_status": asset["status"], "source": "synthetic_work_order_database",
                                  "asset_status_evidence": status_evidence,
                                  "source_scope": "work_order_only; asset status retains its independent observation provenance",
                                  "physical_completion": False})
        self.store.update(proposal)
        return {"proposal": proposal, "outcome": "accepted_workflow_not_repair", "physical_effect": False,
                "idempotency": {"replayed": recovered, "command_request_id": proposal["command_request_id"]}}

    def execute(self, ident, request):
        with self.store.lock:
            proposal = self.store.get(ident)
            bound = proposal.get("execution_request_id")
            if bound and bound != request.request_id:
                raise WorkflowError("execution_request_conflict", "Proposal execution is bound to another caller request ID")
            receipt = self._existing_receipt(proposal)
            if receipt:
                if not bound or proposal["status"] not in {"execution_intent_recorded", "accepted_workflow_not_repair"}:
                    raise WorkflowError("unexpected_command_receipt", "A command receipt exists without this proposal's durable execution intent")
                # Historical receipt recovery, not a new execution. A completed
                # command stays acknowledged after expiry or changed conditions.
                proposal["execution_request_id"] = request.request_id
                return self._complete(proposal, receipt, recovered=True)
            if self.connectors.clock() >= datetime.fromisoformat(proposal["expires_at"]):
                raise WorkflowError("proposal_expired", "Proposal expired before a command was accepted; create a fresh proposal")
            state, asset, condition = self._current(proposal["action"]["asset_id"])
            if condition != proposal["preconditions"]:
                instruction = "inspect the existing work order" if condition["open_work_order_ids"] else "review current conditions before creating a new proposal"
                raise WorkflowError("proposal_preconditions_changed", "Proposal conditions changed; " + instruction,
                                    context=self._conflict_context(condition, proposal["preconditions"]))
            proposal.update(execution_request_id=request.request_id, status="execution_intent_recorded")
            self.store.update(proposal)  # Durable before the separate park transaction.
            result = self.park.act("dispatch_maintenance", proposal["action"]["asset_id"], request_id=proposal["command_request_id"])
            return self._complete(proposal, result["result"], recovered=result["idempotency"]["replayed"])
