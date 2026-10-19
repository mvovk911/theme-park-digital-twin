/* Explicit synthetic maintenance proposals. This module never auto-executes. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  if (!$("workflow-panel")) return;
  const createPaths = {
    current_incident: "/api/workflows/incidents",
    saved_plan: "/api/workflows/proposals",
  };
  let origin = "current_incident",
    incidentAsset = "";
  const key = "aster.maintenance.retry.v1",
    esc = (value) =>
      String(value ?? "").replace(
        /[&<>"']/g,
        (char) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[char],
      );
  const title = (value) =>
    String(value || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  const date = (value) => {
    const d = new Date(value);
    return Number.isFinite(d.getTime())
      ? d.toISOString().slice(0, 19).replace("T", " ") + " UTC"
      : "unavailable";
  };
  const assets = {
    RIDE_COASTER: "Coaster",
    RIDE_WHEEL: "Observation wheel",
    POWER_HUB: "Power hub",
    WATER_PLANT: "Water plant",
  };
  let capability = null,
    evidence = null,
    observation = null,
    observedAt = 0,
    viewPending = false,
    busy = false,
    proposal = null,
    record = {},
    choices = [],
    selected = "",
    selectionKey = "",
    historyOffset = 0,
    historyTotal = 0,
    proposalRenderKey = "",
    storageBlocked = false;
  const id = (prefix) =>
    `${prefix}:${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  function message(text, error = false) {
    $("workflow-message").textContent = text;
    $("workflow-message").classList.toggle("error", error);
    $("workflow-conflict").hidden = true;
  }
  function persist(next) {
    localStorage.setItem(key, JSON.stringify(next));
    record = next;
    storageBlocked = false;
  }
  function uncertain() {
    return !!record.create_uncertain || !!record.execute_uncertain;
  }
  function live() {
    return (
      observation?.mode === "live" &&
      !viewPending &&
      Date.now() - observedAt < 10000
    );
  }
  function expired() {
    return proposal && Date.parse(proposal.expires_at) <= Date.now();
  }
  function accepted() {
    return proposal?.status === "accepted_workflow_not_repair";
  }
  function supported(action) {
    return capability?.supported_actions?.some(
      (rule) =>
        rule.action === action.action &&
        rule.at_minute === action.at_minute &&
        rule.asset_ids.includes(action.asset_id),
    );
  }
  async function request(path, payload) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, {
        cache: "no-store",
        signal: controller.signal,
        ...(payload
          ? {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            }
          : {}),
      });
      let data;
      try {
        data = await response.json();
      } catch (_) {
        throw new Error(
          "Response could not be read; the request may have been accepted.",
        );
      }
      if (!response.ok) {
        const error = new Error(
          data.detail?.message ||
            data.detail ||
            `Service returned ${response.status}`,
        );
        error.code = data.detail?.code;
        error.context = data.detail?.context;
        error.status = response.status;
        throw error;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
  function showConflict(context) {
    if (!context || typeof context !== "object") return;
    const asset = context.asset_id,
      ids = context.current_work_order_ids || [],
      labels = {
        scenario: "Scenario",
        status: "Asset status",
        inspection_status: "Inspection",
        observed_open_work_orders: "Open order count",
        open_work_order_ids: "Open order IDs",
        field_sources: "Source ownership",
        asset_type: "Asset type",
      };
    const value = (item) =>
      Array.isArray(item)
        ? item.map((id) => `#${id}`).join(", ") || "none"
        : item && typeof item === "object"
          ? "source mapping"
          : String(item ?? "none");
    const changes = Object.entries(context.changed_fields || {})
      .map(
        ([field, change]) =>
          `<li>${esc(labels[field] || title(field))}: ${esc(value(change.proposed))} → ${esc(value(change.current))}</li>`,
      )
      .join("");
    const validAsset = /^[A-Z0-9_]+$/.test(asset || "");
    $("workflow-conflict").innerHTML =
      `<strong>${ids.length ? `Existing work order${ids.length > 1 ? "s" : ""}: ${ids.map((id) => `#${esc(id)}`).join(", ")}` : "Current conditions differ from the proposal"}</strong><p>${context.next_step === "inspect_existing_work_order" ? "Inspect the existing work order before requesting another dispatch." : "Review current conditions before creating a fresh proposal."}</p>${changes ? `<ul>${changes}</ul>` : ""}${validAsset ? `<div><button data-workflow-inspect data-asset="${esc(asset)}">Inspect ${esc(assets[asset] || title(asset))} ↗</button><a href="/api/assets/${encodeURIComponent(asset)}" target="_blank" rel="noopener">Open asset and work-order record ↗</a></div>` : ""}`;
    $("workflow-conflict").hidden = false;
  }
  function validProposal(value, expected = null) {
    if (
      !value ||
      !/^[a-f0-9]{32}$/.test(value.id) ||
      value.synthetic !== true ||
      value.physical_effect !== false ||
      value.execution_scope !== "synthetic_dispatch_only" ||
      value.action?.action !== "dispatch_maintenance" ||
      (expected && value.id !== expected)
    )
      throw new Error(
        "Proposal identity or synthetic execution scope could not be verified.",
      );
    return value;
  }
  function creationObservations(value) {
    const frozen = value.creation_observation;
    if (!frozen?.fields) return "";
    const labels = {
      status: "Asset status",
      "maintenance.inspection_status": "Inspection",
      "maintenance.open_work_orders": "Open order count",
    };
    return `<details class="workflow-observations" open><summary>Observations frozen at proposal creation</summary><p>Captured ${esc(date(frozen.captured_at))}. Values and quality below are historical checks, not continuously refreshed telemetry.</p><div>${Object.entries(
      frozen.fields,
    )
      .map(
        ([metric, field]) =>
          `<article><span>${esc(labels[metric] || title(metric))}</span><strong>${esc(title(String(field.value)))} · ${esc(field.quality?.status || "unknown")}</strong><small>${esc(field.quality?.source_id || "source unavailable")} · ${field.quality?.synthetic === true ? "synthetic" : "provenance unavailable"}</small><small>Source ${esc(date(field.quality?.source_timestamp))}</small></article>`,
      )
      .join(
        "",
      )}</div><p>Scenario context: ${esc(title(frozen.scenario_context))}${value.precondition_scope === "target" ? " · global scenario is not an approval condition." : " · checked with this saved-plan proposal."}</p></details>`;
  }
  function assetObservation(readback) {
    const field = readback.asset_status_evidence,
      quality = field?.quality || "unknown";
    const usable =
      field &&
      ["good", "stale", "uncertain"].includes(quality) &&
      typeof field.value === "string";
    const label = !usable
      ? "Asset status unavailable"
      : quality === "good"
        ? `Observed ${title(field.value)} · quality good`
        : `Last observed ${title(field.value)} · ${quality}`;
    return `<div class="workflow-asset-evidence ${quality === "good" ? "" : "warning"}"><span>INDEPENDENT ASSET OBSERVATION</span><strong>${esc(label)}</strong><small>Source timestamp ${esc(date(field?.source_timestamp))} · ${esc(field?.source_id || "source unavailable")} · ${field?.synthetic === true ? "synthetic source" : "source provenance unavailable"}</small><small>Quality shown at the recorded readback. The work-order database timestamp does not refresh this asset observation.</small></div>`;
  }
  function render() {
    choices = (evidence?.branches || []).flatMap((branch) =>
      (branch.action_schedule || []).map((action, index) => ({
        key: `${branch.id}:${index}`,
        branch_id: branch.id,
        action_index: index,
        label: `${branch.label} · ${title(action.action)} · ${assets[action.asset_id] || title(action.asset_id)}`,
        action,
      })),
    );
    const newKey = JSON.stringify([
      evidence?.bundle_id,
      evidence?.saved,
      choices,
      capability?.supported_actions,
    ]);
    if (newKey !== selectionKey) {
      selectionKey = newKey;
      const allowed = choices.filter((item) => supported(item.action));
      if (!allowed.some((item) => item.key === selected))
        selected = allowed[0]?.key || "";
      $("workflow-action").innerHTML = choices.length
        ? (allowed.length
            ? ""
            : '<option value="">No supported action in this comparison</option>') +
          choices
            .map(
              (item) =>
                `<option value="${esc(item.key)}" ${supported(item.action) ? "" : "disabled"}>${esc(item.label)}${supported(item.action) ? "" : " · no executor"}</option>`,
            )
            .join("")
        : '<option value="">Save a comparison to review its actions</option>';
      $("workflow-action").value = selected;
    }
    if (proposal && !evidence) {
      $("workflow-action").innerHTML =
        `<option>Recovered dispatch · ${esc(assets[proposal.action.asset_id] || proposal.action.asset_id)}</option>`;
    }
    const unresolvedCreate =
      record.create_payload && !proposal && !record.create_rejected;
    const locked = busy || !!proposal || !!unresolvedCreate;
    $("workflow-origin").value = origin;
    $("workflow-origin").disabled = locked;
    $("workflow-incident-label").hidden = origin !== "current_incident";
    $("workflow-saved-label").hidden = origin !== "saved_plan";
    $("workflow-incident-asset").value = incidentAsset;
    $("workflow-incident-asset").disabled = locked;
    $("workflow-rationale-label").hidden =
      origin !== "current_incident" || !evidence?.saved;
    $("workflow-rationale").disabled = locked;
    const incidentSupported =
      capability?.proposal_origins?.current_incident &&
      supported({
        action: "dispatch_maintenance",
        at_minute: 0,
        asset_id: incidentAsset,
      });
    const readyChoice =
      origin === "current_incident"
        ? incidentSupported
        : evidence?.saved && selected;
    $("workflow-action").disabled = busy || !!proposal || !!unresolvedCreate;
    $("workflow-create").textContent = unresolvedCreate
      ? "Retry same proposal request"
      : "Create proposal";
    $("workflow-create").disabled =
      storageBlocked ||
      busy ||
      !capability ||
      !live() ||
      !!proposal ||
      (!unresolvedCreate && !readyChoice);
    $("workflow-support").textContent = evidence
      ? `${evidence.saved ? "Saved evidence" : "Save this comparison first"} · scenario ${title(evidence.scenario)} / current ${title(observation?.scenario) || "unavailable"}. Only immediate maintenance dispatch has an executor; other actions remain modeled options.`
      : "Open or save a comparison containing immediate maintenance dispatch. Historical hashes and shortlist status do not authorize execution.";
    if (origin === "current_incident")
      $("workflow-support").textContent =
        "The server checks this asset’s current fault or inspection issue, fresh source observations and existing work orders. No forecast or saved comparison is required.";
    if (proposal && !evidence)
      $("workflow-support").textContent =
        "Durable proposal. Its original target, optional rationale and retry identities remain attached; reopening does not execute it.";
    $("workflow-proposal").hidden = !proposal;
    $("workflow-execute").disabled =
      storageBlocked ||
      busy ||
      !capability ||
      !live() ||
      !proposal ||
      !!record.terminal_rejection ||
      (expired() &&
        !record.execute_request_id &&
        !proposal.execution_request_id);
    $("workflow-execute").textContent = accepted()
      ? "Verify receipt & readback again"
      : record.execute_request_id || proposal?.execution_request_id
        ? "Retry same work-order request"
        : "Execute synthetic work order";
    $("workflow-recover").disabled = busy || !record.proposal_id;
    $("workflow-history").disabled = busy || uncertain();
    $("workflow-new").hidden = !(proposal || record.create_rejected);
    $("workflow-new").disabled =
      busy ||
      uncertain() ||
      (!accepted() &&
        !record.terminal_rejection &&
        !record.create_rejected &&
        !expired());
    if (!proposal) {
      proposalRenderKey = "";
      return;
    }
    const p = proposal.preconditions || {},
      remaining = Math.max(
        0,
        Math.ceil((Date.parse(proposal.expires_at) - Date.now()) / 1000),
      );
    const nextRenderKey = JSON.stringify(proposal);
    if (proposalRenderKey === nextRenderKey) {
      const badge = $("workflow-proposal").querySelector(".workflow-expiry");
      badge.textContent = accepted()
        ? "Recorded acceptance"
        : expired()
          ? "Proposal expired"
          : `${remaining}s remaining`;
      badge.classList.toggle("expired", expired());
      return;
    }
    proposalRenderKey = nextRenderKey;
    const receipt = proposal.receipt,
      readback = proposal.readback;
    $("workflow-proposal").innerHTML =
      `<div class="workflow-proposal-heading"><div><small>${accepted() ? "DURABLE ACKNOWLEDGEMENT" : "PROPOSAL · SEPARATE EXECUTION REQUIRED"}</small><h4>${accepted() ? `Work order accepted · ${esc(assets[proposal.action.asset_id] || proposal.action.asset_id)} · repair not performed` : `Dispatch maintenance · ${esc(assets[proposal.action.asset_id] || proposal.action.asset_id)}`}</h4></div><span class="workflow-expiry ${expired() ? "expired" : ""}">${accepted() ? "Recorded acceptance" : expired() ? "Proposal expired" : `${remaining}s remaining`}</span></div><div class="workflow-checks"><div><span>${proposal.precondition_scope === "target" ? "Scenario context" : "Scenario checked"}</span><strong>${esc(title(p.scenario || proposal.creation_observation?.scenario_context))}</strong></div><div><span>Asset status</span><strong>${esc(title(p.status))}</strong></div><div><span>Inspection</span><strong>${esc(title(p.inspection_status))}</strong></div><div><span>Orders at creation</span><strong>${esc(p.observed_open_work_orders)}</strong></div></div><p class="workflow-check-note">Checked at proposal creation ${esc(date(proposal.created_at))}; relevant conditions are checked again immediately before a new dispatch. Expires ${esc(date(proposal.expires_at))}. Countdown uses this browser’s clock; the server enforces expiry.</p>${creationObservations(proposal)}${receipt && readback ? `<div class="workflow-result"><div><span>ORIGINAL RECEIPT</span><strong>${esc(title(receipt.lifecycle || receipt.acknowledgement))}</strong><small>Work order ${esc(receipt.work_order_id)} · accepted ${esc(date(receipt.applied_at || receipt.timestamp))}</small></div><div><span>RECORDED DATABASE READBACK</span><strong>${esc(title(readback.work_order?.status))} work order</strong><small>Work-order record checked ${esc(date(readback.observed_at))} · physical completion: false</small></div></div>${assetObservation(readback)}<p class="workflow-not-repair">Accepted workflow, not a repair. This dispatch does not restore ride availability or establish that maintenance was completed.</p>` : ""}<details class="workflow-identities"><summary>Proposal & retry identity</summary><code>Proposal ${esc(proposal.id)}<br>Create ${esc(proposal.create_request_id)}<br>Execution ${esc(record.execute_request_id || proposal.execution_request_id || "not requested")}<br>Evidence ${esc(proposal.evidence_refs?.bundle_id || proposal.evidence_refs?.rationale_bundle_id || "none · current incident")}</code></details>`;
  }
  function receive(value, expected = null) {
    const next = validProposal(value, expected);
    if (
      record.execute_request_id &&
      next.execution_request_id &&
      record.execute_request_id !== next.execution_request_id
    )
      throw new Error(
        "The saved execution identity differs from this browser. The record was not rebound.",
      );
    persist({
      ...record,
      proposal_id: next.id,
      create_uncertain: false,
      execute_request_id:
        record.execute_request_id || next.execution_request_id || null,
      execute_uncertain: next.status === "execution_intent_recorded",
      create_rejected: false,
    });
    proposal = next;
    origin =
      next.origin === "current_incident" ? "current_incident" : "saved_plan";
    incidentAsset = next.action.asset_id;
  }
  async function recover() {
    if (!record.proposal_id || busy) return;
    busy = true;
    render();
    try {
      const data = await request(
        `/api/workflows/proposals/${record.proposal_id}`,
      );
      receive(data.proposal, record.proposal_id);
      message(
        accepted()
          ? "Recorded receipt and most recent readback reopened. No execution request was sent."
          : record.execute_uncertain
            ? "Execution intent is recorded. Retry the same work-order request to recover its receipt."
            : record.terminal_rejection
              ? "Previous execution was rejected. Review current conditions before creating a fresh proposal."
              : "Durable proposal reopened. Execution still requires a separate explicit click.",
      );
    } catch (error) {
      message(`Proposal could not be reopened: ${error.message}`, true);
    } finally {
      busy = false;
      render();
    }
  }
  $("workflow-conflict").addEventListener("click", (event) => {
    if (event.target.closest("[data-workflow-inspect]"))
      $("operations-view").scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
  });
  $("workflow-origin").addEventListener("change", (event) => {
    origin = event.target.value;
    render();
  });
  $("workflow-incident-asset").addEventListener("change", (event) => {
    incidentAsset = event.target.value;
    render();
  });
  document.addEventListener("click", (event) => {
    const entry = event.target.closest("[data-workflow-prepare]");
    if (!entry || entry.disabled) return;
    $("workflow-panel").open = true;
    $("workflow-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    if (
      busy ||
      uncertain() ||
      storageBlocked ||
      (proposal && !accepted() && !record.terminal_rejection && !expired())
    ) {
      message(
        "An existing proposal or uncertain request is retained. Resolve or recover it before preparing another target.",
        true,
      );
      return;
    }
    try {
      persist({});
      proposal = null;
      origin = "current_incident";
      incidentAsset = entry.dataset.workflowPrepare;
      $("workflow-rationale").checked = false;
      message(
        "Target selected. No proposal or work order has been created. Review the asset, then click Create proposal.",
      );
      render();
    } catch (error) {
      message(`No request sent: ${error.message}`, true);
    }
  });
  $("workflow-action").addEventListener("change", (event) => {
    selected = event.target.value;
    render();
  });
  $("workflow-create").addEventListener("click", async () => {
    if (busy || !live() || proposal) return;
    try {
      if (!record.create_payload || record.create_rejected) {
        let payload;
        if (origin === "current_incident") {
          if (
            !capability?.proposal_origins?.current_incident ||
            !supported({
              action: "dispatch_maintenance",
              at_minute: 0,
              asset_id: incidentAsset,
            })
          )
            return;
          payload = {
            asset_id: incidentAsset,
            request_id: id("incident"),
            ttl_seconds: 120,
          };
          if ($("workflow-rationale").checked && evidence?.saved)
            payload.rationale_bundle_id = evidence.bundle_id;
        } else {
          const choice = choices.find((item) => item.key === selected);
          if (!evidence?.saved || !choice || !supported(choice.action)) return;
          payload = {
            bundle_id: evidence.bundle_id,
            branch_id: choice.branch_id,
            action_index: choice.action_index,
            request_id: id("create"),
            ttl_seconds: 120,
          };
        }
        persist({
          create_endpoint: createPaths[origin],
          create_payload: payload,
          create_uncertain: true,
        });
      } else persist({ ...record, create_uncertain: true });
    } catch (error) {
      message(
        `No request sent: retry identity could not be retained in browser storage. ${error.message}`,
        true,
      );
      return;
    }
    busy = true;
    render();
    message(
      "Checking current target maintenance need, source freshness and work orders…",
    );
    try {
      const endpoint = record.create_endpoint || createPaths.saved_plan;
      if (!Object.values(createPaths).includes(endpoint))
        throw new Error(
          "Unknown retained creation endpoint. Recover the durable record before writing.",
        );
      const data = await request(endpoint, record.create_payload),
        p = validProposal(data.proposal),
        payload = record.create_payload;
      const matches =
        endpoint === createPaths.current_incident
          ? p.origin === "current_incident" &&
            p.precondition_scope === "target" &&
            p.action.asset_id === payload.asset_id &&
            (p.evidence_refs?.rationale_bundle_id || null) ===
              (payload.rationale_bundle_id || null)
          : p.evidence_refs?.bundle_id === payload.bundle_id &&
            p.evidence_refs?.branch_id === payload.branch_id &&
            p.evidence_refs?.action_index === payload.action_index;
      if (p.create_request_id !== payload.request_id || !matches)
        throw new Error(
          "Proposal acknowledgement does not match the retained request.",
        );
      receive(p);
      message(
        data.idempotency?.replayed
          ? "Original proposal recovered with the same request identity. Its expiry was not renewed."
          : "Proposal created for 120 seconds. Review its checks, then explicitly execute if appropriate.",
      );
    } catch (error) {
      if (error.status >= 400 && error.status < 500)
        try {
          persist({
            ...record,
            create_rejected: true,
            create_uncertain: false,
          });
        } catch (_) {}
      message(
        `${error.status ? "Proposal rejected" : "Acceptance unknown"}: ${error.message}${record.create_uncertain ? " Retry the same proposal request; do not create a new identity." : ""}`,
        true,
      );
      showConflict(error.context);
    } finally {
      busy = false;
      render();
    }
  });
  $("workflow-execute").addEventListener("click", async () => {
    if (busy || !live() || !proposal || record.terminal_rejection) return;
    try {
      persist({
        ...record,
        execute_request_id:
          record.execute_request_id ||
          proposal.execution_request_id ||
          id("execute"),
        execute_uncertain: true,
      });
    } catch (error) {
      message(
        `No request sent: execution identity could not be retained in browser storage. ${error.message}`,
        true,
      );
      return;
    }
    busy = true;
    render();
    message(
      "Checking the exact proposal and requesting the synthetic work order…",
    );
    try {
      const data = await request(
        `/api/workflows/proposals/${proposal.id}/execute`,
        { request_id: record.execute_request_id },
      );
      const p = validProposal(data.proposal, proposal.id);
      if (
        data.outcome !== "accepted_workflow_not_repair" ||
        data.physical_effect !== false ||
        p.execution_request_id !== record.execute_request_id ||
        p.readback?.physical_completion !== false ||
        !p.receipt?.work_order_id ||
        p.receipt.work_order_id !== p.readback?.work_order?.id
      )
        throw new Error(
          "Acceptance and work-order readback could not be associated. Keep the same retry identity.",
        );
      receive(p);
      persist({ ...record, execute_uncertain: false });
      message(
        data.idempotency?.replayed
          ? "Existing command receipt recovered; no duplicate dispatch. Readback was verified again."
          : "Synthetic work order accepted and read back. The asset has not been repaired or reopened.",
      );
    } catch (error) {
      if (
        ["proposal_expired", "proposal_preconditions_changed"].includes(
          error.code,
        )
      )
        try {
          persist({
            ...record,
            terminal_rejection: true,
            execute_uncertain: false,
          });
        } catch (_) {}
      else if (
        error.status >= 400 &&
        error.status < 500 &&
        !["work_order_readback_missing", "execution_request_conflict"].includes(
          error.code,
        )
      )
        try {
          persist({ ...record, execute_uncertain: false });
        } catch (_) {}
      message(
        `${error.status ? "Execution blocked" : "Acceptance unknown"}: ${error.message}${record.execute_uncertain ? " Retry with the retained execution identity to recover safely." : ""}`,
        true,
      );
      showConflict(error.context);
    } finally {
      busy = false;
      render();
    }
  });
  $("workflow-recover").addEventListener("click", recover);
  $("workflow-new").addEventListener("click", () => {
    if (busy || uncertain() || $("workflow-new").disabled) return;
    try {
      persist({});
      proposal = null;
      message(
        "Review fresh current conditions by creating a new proposal. Previous records remain in the durable history.",
      );
      render();
    } catch (error) {
      message(error.message, true);
    }
  });
  async function history() {
    if (busy || uncertain()) return;
    busy = true;
    render();
    try {
      const data = await request(
        `/api/workflows/proposals?limit=20&offset=${historyOffset}`,
      );
      if (!Array.isArray(data.items))
        throw new Error("Unexpected proposal history.");
      historyTotal = data.total;
      $("workflow-history-list").hidden = false;
      $("workflow-history-list").innerHTML =
        data.items
          .map(
            (p) =>
              `<button data-workflow-id="${esc(p.id)}"><strong>${esc(assets[p.action?.asset_id] || p.action?.asset_id)} · ${esc(title(p.status))}</strong><small>${esc(date(p.created_at))} · ${esc(p.id.slice(0, 10))}</small></button>`,
          )
          .join("") || "<p>No stored proposals.</p>";
      $("workflow-history-list").innerHTML +=
        `<div class="workflow-history-pages"><button data-workflow-page="previous" ${historyOffset === 0 ? "disabled" : ""}>← Newer</button><button data-workflow-page="next" ${historyOffset + 20 >= historyTotal ? "disabled" : ""}>Older →</button></div>`;
    } catch (error) {
      message(`History unavailable: ${error.message}`, true);
    } finally {
      busy = false;
      render();
    }
  }
  $("workflow-history").addEventListener("click", () => {
    historyOffset = 0;
    history();
  });
  $("workflow-history-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || busy || uncertain()) return;
    if (button.dataset.workflowPage) {
      historyOffset = Math.max(
        0,
        historyOffset + (button.dataset.workflowPage === "next" ? 20 : -20),
      );
      return history();
    }
    const ident = button.dataset.workflowId;
    if (!/^[a-f0-9]{32}$/.test(ident || "")) return;
    try {
      persist({ proposal_id: ident });
      proposal = null;
      await recover();
    } catch (error) {
      message(error.message, true);
    }
  });
  document.addEventListener("park:planning-evidence", (event) => {
    evidence = event.detail;
    render();
  });
  document.addEventListener("park:state", (event) => {
    const prior = observation?.mode;
    observation = event.detail;
    observedAt = Date.now();
    if (prior && prior !== observation.mode)
      message(
        observation.mode === "replay"
          ? "Recorded view: proposal creation and execution are disabled. Historical records remain readable."
          : "Live view restored. Current conditions will be rechecked before dispatch.",
      );
    render();
  });
  document.addEventListener("park:view-pending", (event) => {
    viewPending = !!event.detail;
    render();
  });
  (async () => {
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        if (raw.length > 10000)
          throw new Error("Retained retry record exceeds its size limit.");
        record = JSON.parse(raw);
        if (!record || typeof record !== "object")
          throw new Error("Invalid retry record.");
        if (
          record.create_endpoint &&
          !Object.values(createPaths).includes(record.create_endpoint)
        )
          throw new Error("Unknown creation endpoint.");
        if (record.create_payload) {
          origin =
            record.create_endpoint === createPaths.current_incident
              ? "current_incident"
              : "saved_plan";
          incidentAsset = record.create_payload.asset_id || "";
        }
      }
    } catch (error) {
      message(
        `Retry record could not be read; writes are blocked until a durable proposal is explicitly recovered: ${error.message}`,
        true,
      );
      record = {};
      storageBlocked = true;
    }
    try {
      const data = await request("/api/workflows/capabilities");
      if (
        data.synthetic !== true ||
        data.physical_control !== false ||
        data.evidence_is_authority !== false
      )
        throw new Error("Unsupported workflow scope.");
      capability = data;
      if (!storageBlocked)
        message(
          record.create_uncertain
            ? "A proposal request has an unknown outcome. Retry it with its retained identity."
            : "Select a current incident, or use a saved comparison. Nothing executes automatically.",
        );
      if (record.proposal_id) await recover();
    } catch (error) {
      message(`Workflow service unavailable: ${error.message}`, true);
    } finally {
      render();
    }
    setInterval(render, 1000);
  })();
})();
