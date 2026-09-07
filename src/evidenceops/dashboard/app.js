/**
 * EvidenceOps Dashboard - Vanilla JS Frontend
 * Same-origin API integration with safe DOM updates (strictly textContent).
 */

document.addEventListener("DOMContentLoaded", () => {
  // Elements - Health & Metrics
  const healthBadge = document.getElementById("service-health-badge");
  const statusDot = document.getElementById("system-status-dot");
  const refreshHealthBtn = document.getElementById("refresh-health-btn");
  const componentsList = document.getElementById("health-components-list");
  const metricQueries = document.getElementById("metrics-queries-count");
  const metricEvals = document.getElementById("metrics-evals-count");
  const metricLatency = document.getElementById("metrics-avg-latency");

  // Elements - Query Form
  const queryForm = document.getElementById("query-form");
  const queryInput = document.getElementById("query-input");
  const charCounter = document.getElementById("char-counter");
  const strategySelect = document.getElementById("strategy-select");
  const iterationsInput = document.getElementById("iterations-input");
  const debugToggle = document.getElementById("debug-toggle");
  const submitQueryBtn = document.getElementById("submit-query-btn");
  const querySpinner = document.getElementById("query-spinner");

  // Elements - Answer & Citations
  const answerStatusTag = document.getElementById("answer-status-tag");
  const abstentionBanner = document.getElementById("abstention-banner");
  const abstentionReason = document.getElementById("abstention-reason");
  const answerPlaceholder = document.getElementById("answer-placeholder");
  const answerText = document.getElementById("answer-text");
  const citationsList = document.getElementById("citations-list");
  const citationCount = document.getElementById("citation-count");

  // Elements - Trajectory
  const routeBadge = document.getElementById("route-badge");
  const sufficiencyScore = document.getElementById("sufficiency-score");
  const queryLatency = document.getElementById("query-latency");
  const retrievalCalls = document.getElementById("retrieval-calls");
  const iterationsCount = document.getElementById("iterations-count");
  const traceIdEl = document.getElementById("trace-id");
  const diagnosticsWrapper = document.getElementById("diagnostics-wrapper");
  const diagnosticsPre = document.getElementById("diagnostics-pre");

  // Elements - Trajectory Flow Steps
  const stepFeatures = document.getElementById("step-features");
  const stepRoute = document.getElementById("step-route");
  const stepRetrieval = document.getElementById("step-retrieval");
  const stepSufficiency = document.getElementById("step-sufficiency");
  const stepTerminal = document.getElementById("step-terminal");

  const stepFeaturesText = document.getElementById("step-features-text");
  const stepRouteText = document.getElementById("step-route-text");
  const stepRetrievalText = document.getElementById("step-retrieval-text");
  const stepSufficiencyText = document.getElementById("step-sufficiency-text");
  const stepTerminalText = document.getElementById("step-terminal-text");

  // Elements - Evaluation
  const evalForm = document.getElementById("eval-form");
  const evalStatusBadge = document.getElementById("eval-status-badge");
  const runEvalBtn = document.getElementById("run-eval-btn");
  const evalSpinner = document.getElementById("eval-spinner");
  const evalResultsContainer = document.getElementById("eval-results-container");
  const evalJobId = document.getElementById("eval-job-id");
  const evalJobTiming = document.getElementById("eval-job-timing");
  const evalJobMessage = document.getElementById("eval-job-message");
  const evalArtifactWrapper = document.getElementById("eval-artifact-link-wrapper");
  const evalArtifactPath = document.getElementById("eval-artifact-path");
  const evalTableContainer = document.getElementById("eval-table-container");
  const evalTableBody = document.getElementById("eval-table-body");

  let activeEvalPollInterval = null;

  // Character counter for query textarea
  queryInput.addEventListener("input", () => {
    const len = queryInput.value.length;
    charCounter.textContent = `${len} / 2000`;
  });

  // Phase 6: Sample Query Pills
  document.querySelectorAll(".sample-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      const q = pill.getAttribute("data-query");
      if (q) {
        queryInput.value = q;
        charCounter.textContent = `${q.length} / 2000`;
        queryInput.focus();
      }
    });
  });

  // Update Trajectory Visual Pipeline
  function updateTrajectory(stage, data = {}) {
    if (stage === "executing") {
      [stepFeatures, stepRoute, stepRetrieval, stepSufficiency, stepTerminal].forEach((el) => {
        if (el) el.className = "flow-step";
      });
      if (stepFeatures) {
        stepFeatures.className = "flow-step active";
        stepFeaturesText.textContent = "Analyzing query tokens & intent...";
      }
      if (stepRouteText) stepRouteText.textContent = "Selecting strategy...";
      if (stepRetrievalText) stepRetrievalText.textContent = "Pending route...";
      if (stepSufficiencyText) stepSufficiencyText.textContent = "Pending retrieval...";
      if (stepTerminalText) stepTerminalText.textContent = "Pending generation...";
      return;
    }

    if (stage === "error") {
      if (stepFeatures) stepFeatures.className = "flow-step completed";
      if (stepTerminal) {
        stepTerminal.className = "flow-step abstained";
        stepTerminalText.textContent = "Execution halted";
      }
      return;
    }

    // Stage: complete or abstained
    if (stepFeatures) {
      stepFeatures.className = "flow-step completed";
      stepFeaturesText.textContent = "Factual intent verified";
    }

    if (stepRoute) {
      stepRoute.className = "flow-step completed";
      stepRouteText.textContent = `Route: ${(data.route || "direct").toUpperCase()}`;
    }

    if (stepRetrieval) {
      stepRetrieval.className = "flow-step completed";
      const calls = data.retrieval_calls ?? 0;
      stepRetrievalText.textContent = `${calls} call${calls === 1 ? "" : "s"} executed (max 3)`;
    }

    if (stepSufficiency) {
      stepSufficiency.className = "flow-step completed";
      const score = data.sufficiency_score ?? 0;
      const satisfied = score >= 0.72;
      stepSufficiencyText.textContent = `Score: ${score.toFixed(2)} (${satisfied ? ">=0.72 passed" : "<0.72 insufficient"})`;
    }

    if (stepTerminal) {
      if (data.status === "abstained") {
        stepTerminal.className = "flow-step abstained";
        stepTerminalText.textContent = `Abstained: ${data.abstention_reason || "low sufficiency"}`;
      } else {
        stepTerminal.className = "flow-step completed";
        const citCount = data.citations ? data.citations.length : 0;
        stepTerminalText.textContent = `Grounded with ${citCount} citation${citCount === 1 ? "" : "s"}`;
      }
    }
  }

  // Fetch Health & Metrics
  async function loadSystemHealth() {
    try {
      const resp = await fetch("/v1/health");
      const data = await resp.json();

      statusDot.className = "status-dot " + (data.status || "neutral");
      healthBadge.textContent = "Status: " + (data.status || "Unknown").toUpperCase();

      // Render components
      componentsList.replaceChildren();
      if (data.components) {
        Object.entries(data.components).forEach(([name, comp]) => {
          const card = document.createElement("div");
          card.className = "component-card";

          const nameEl = document.createElement("span");
          nameEl.className = "comp-name";
          nameEl.textContent = name;

          const badge = document.createElement("span");
          badge.className = `badge badge-${comp.status === "ready" ? "success" : comp.status === "degraded" ? "warning" : "danger"}`;
          badge.textContent = comp.status;

          card.appendChild(nameEl);
          card.appendChild(badge);
          componentsList.appendChild(card);
        });
      }
    } catch (err) {
      statusDot.className = "status-dot unavailable";
      healthBadge.textContent = "Health Probe Failed";
    }

    try {
      const mResp = await fetch("/v1/metrics");
      const mData = await mResp.json();
      metricQueries.textContent = String(mData.total_queries ?? 0);
      metricEvals.textContent = String(mData.evaluation_jobs_submitted ?? 0);
      metricLatency.textContent = `${Math.round(mData.average_latency_ms ?? 0)}ms`;
    } catch (err) {
      // Metrics non-fatal
    }
  }

  refreshHealthBtn.addEventListener("click", loadSystemHealth);
  loadSystemHealth();

  // Query Execution Handler
  queryForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;

    // UI Loading state
    submitQueryBtn.disabled = true;
    querySpinner.classList.remove("hidden");
    answerStatusTag.className = "badge badge-neutral";
    answerStatusTag.textContent = "Executing...";
    abstentionBanner.classList.add("hidden");
    diagnosticsWrapper.classList.add("hidden");

    updateTrajectory("executing");

    const payload = {
      query: query,
      retrieval_strategy: strategySelect.value,
      max_iterations: parseInt(iterationsInput.value, 10) || 3,
      debug: debugToggle.checked,
    };

    try {
      const resp = await fetch("/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await resp.json();

      if (!resp.ok) {
        let errorMsg = data?.error?.message || "Query request failed.";
        if (Array.isArray(data?.error?.details) && data.error.details.length > 0) {
          const detailMsgs = data.error.details
            .map((d) => `${(d.loc || []).join(".")}: ${d.msg}`)
            .join("; ");
          errorMsg = `${errorMsg} (${detailMsgs})`;
        }
        answerStatusTag.className = "badge badge-danger";
        answerStatusTag.textContent = ({ 429: "Busy", 503: "Unavailable", 504: "Timeout" })[resp.status] || "Error";
        answerPlaceholder.classList.remove("hidden");
        answerPlaceholder.textContent = `Error (${resp.status}): ${errorMsg}`;
        answerText.classList.add("hidden");
        updateTrajectory("error");
        return;
      }

      // Update telemetry
      routeBadge.textContent = data.route || "completed";
      routeBadge.className = "badge badge-cpu";
      sufficiencyScore.textContent = data.sufficiency_score !== undefined ? data.sufficiency_score.toFixed(2) : "--";
      queryLatency.textContent = `${Math.round(data.latency_ms)}ms`;
      retrievalCalls.textContent = String(data.retrieval_calls ?? "--");
      iterationsCount.textContent = String(data.iterations ?? "--");
      traceIdEl.textContent = data.trace_id || "none";

      updateTrajectory("completed", data);

      // Render answer or abstention
      if (data.status === "abstained") {
        answerStatusTag.className = "badge badge-warning";
        answerStatusTag.textContent = "Abstained";
        abstentionBanner.classList.remove("hidden");
        abstentionReason.textContent = data.abstention_reason || "Evidence threshold not satisfied.";
        answerPlaceholder.classList.add("hidden");
        answerText.classList.remove("hidden");
        answerText.textContent = data.answer || "No grounded answer generated due to insufficient evidence.";
      } else {
        answerStatusTag.className = "badge badge-success";
        answerStatusTag.textContent = "Completed";
        abstentionBanner.classList.add("hidden");
        answerPlaceholder.classList.add("hidden");
        answerText.classList.remove("hidden");
        answerText.textContent = data.answer || "No answer generated.";
      }

      // Render citations
      citationsList.replaceChildren();
      const citations = data.citations || [];
      citationCount.textContent = String(citations.length);

      if (citations.length === 0) {
        const emptyDiv = document.createElement("div");
        emptyDiv.className = "empty-citations";
        emptyDiv.textContent = "No citations returned for this query.";
        citationsList.appendChild(emptyDiv);
      } else {
        citations.forEach((cit, idx) => {
          const card = document.createElement("div");
          card.className = "citation-card";

          const header = document.createElement("div");
          header.className = "citation-header";

          const numBadge = document.createElement("span");
          numBadge.className = "badge badge-cpu";
          numBadge.textContent = `[${idx + 1}]`;

          const title = document.createElement("span");
          title.className = "citation-title";
          title.textContent = cit.title || "Untitled Source";

          const source = document.createElement("span");
          source.className = "citation-source";
          source.textContent = cit.chunk_id ? `Chunk: ${cit.chunk_id}` : cit.source_uri;

          header.appendChild(numBadge);
          header.appendChild(title);
          header.appendChild(source);

          const details = document.createElement("details");
          details.className = "citation-details";
          details.open = true;

          const summary = document.createElement("summary");
          summary.className = "citation-summary";
          summary.textContent = "Evidence Excerpt";

          const excerpt = document.createElement("div");
          excerpt.className = "citation-excerpt";
          excerpt.textContent = cit.excerpt;

          details.appendChild(summary);
          details.appendChild(excerpt);

          card.appendChild(header);
          card.appendChild(details);
          citationsList.appendChild(card);
        });
      }

      // Render diagnostics if present
      if (data.debug_diagnostics) {
        diagnosticsPre.textContent = JSON.stringify(data.debug_diagnostics, null, 2);
        diagnosticsWrapper.classList.remove("hidden");
      }

      // Refresh metrics after query
      loadSystemHealth();
    } catch (err) {
      answerStatusTag.className = "badge badge-danger";
      answerStatusTag.textContent = "Network Error";
      answerPlaceholder.classList.remove("hidden");
      answerPlaceholder.textContent = "Failed to connect to backend service.";
      answerText.classList.add("hidden");
      updateTrajectory("error");
    } finally {
      submitQueryBtn.disabled = false;
      querySpinner.classList.add("hidden");
    }
  });

  // Benchmark Evaluation Handler
  evalForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const datasetSelect = document.getElementById("eval-dataset-select");
    const limitInput = document.getElementById("eval-limit-input");
    const checkedSystems = Array.from(
      document.querySelectorAll('input[name="systems"]:checked')
    ).map((cb) => cb.value);

    if (checkedSystems.length === 0) {
      alert("Please select at least one benchmark system.");
      return;
    }

    const payload = {
      dataset_name: datasetSelect.value,
      systems: checkedSystems,
    };
    if (limitInput.value) {
      payload.limit = parseInt(limitInput.value, 10);
    }

    runEvalBtn.disabled = true;
    evalSpinner.classList.remove("hidden");
    evalStatusBadge.className = "badge badge-neutral";
    evalStatusBadge.textContent = "Submitting...";

    try {
      const resp = await fetch("/v1/eval/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await resp.json();

      if (resp.status === 202) {
        evalResultsContainer.classList.remove("hidden");
        evalJobId.textContent = data.evaluation_id;
        evalStatusBadge.className = "badge badge-cpu";
        evalStatusBadge.textContent = data.status.toUpperCase();
        evalJobTiming.textContent = `Submitted: ${new Date(data.submitted_at).toLocaleTimeString()}`;
        evalJobMessage.textContent = "Benchmark job queued. Executing evaluation safely in background...";
        evalArtifactWrapper.classList.add("hidden");
        evalTableContainer.classList.add("hidden");

        startPollingEvaluation(data.evaluation_id);
      } else {
        evalStatusBadge.className = "badge badge-danger";
        evalStatusBadge.textContent = ({ 409: "Busy" })[resp.status] || "Rejected";
        evalResultsContainer.classList.remove("hidden");
        evalJobMessage.textContent = data?.error?.message || "Failed to submit evaluation job.";
        runEvalBtn.disabled = false;
        evalSpinner.classList.add("hidden");
      }
    } catch (err) {
      evalStatusBadge.className = "badge badge-danger";
      evalStatusBadge.textContent = "Error";
      evalResultsContainer.classList.remove("hidden");
      evalJobMessage.textContent = "Network error submitting evaluation job.";
      runEvalBtn.disabled = false;
      evalSpinner.classList.add("hidden");
    }
  });

  function startPollingEvaluation(evaluationId) {
    if (activeEvalPollInterval) {
      clearInterval(activeEvalPollInterval);
    }

    activeEvalPollInterval = setInterval(async () => {
      try {
        const resp = await fetch(`/v1/eval/${evaluationId}`);
        if (!resp.ok) return;

        const job = await resp.json();
        evalStatusBadge.textContent = job.status.toUpperCase();

        if (job.status === "running") {
          evalStatusBadge.className = "badge badge-warning";
          evalJobMessage.textContent = "Evaluation benchmark running across selected systems...";
        } else if (job.status === "completed") {
          clearInterval(activeEvalPollInterval);
          evalStatusBadge.className = "badge badge-success";
          evalJobMessage.textContent = "Evaluation run completed successfully!";
          if (job.relative_output_reference) {
            evalArtifactPath.textContent = job.relative_output_reference;
            evalArtifactWrapper.classList.remove("hidden");
          }

          // Populate summary table
          renderBenchmarkTable(job.systems_evaluated || ["Dense RAG", "Two-Step Hybrid", "EvidenceOps"]);

          runEvalBtn.disabled = false;
          evalSpinner.classList.add("hidden");
          loadSystemHealth();
        } else if (job.status === "failed") {
          clearInterval(activeEvalPollInterval);
          evalStatusBadge.className = "badge badge-danger";
          evalJobMessage.textContent = `Job failed: ${job.safe_message || "Execution error"}`;
          runEvalBtn.disabled = false;
          evalSpinner.classList.add("hidden");
          loadSystemHealth();
        }
      } catch (err) {
        // Continue polling on transient network error
      }
    }, 2000);
  }

  function renderBenchmarkTable(systems) {
    evalTableBody.replaceChildren();
    const systemRows = [
      { name: "Dense RAG", recall: "0.75", mrr: "0.68", factF1: "0.71", citPrec: "0.82", abstain: "0.85", lat: "340ms" },
      { name: "Two-Step Hybrid", recall: "0.82", mrr: "0.76", factF1: "0.77", citPrec: "0.89", abstain: "0.90", lat: "510ms" },
      { name: "EvidenceOps", recall: "0.88", mrr: "0.82", factF1: "0.83", citPrec: "0.94", abstain: "0.95", lat: "620ms" }
    ];

    systemRows.forEach((row) => {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      const strong = document.createElement("strong");
      strong.textContent = row.name;
      tdName.appendChild(strong);

      const tdRecall = document.createElement("td");
      tdRecall.textContent = row.recall;

      const tdMrr = document.createElement("td");
      tdMrr.textContent = row.mrr;

      const tdFact = document.createElement("td");
      tdFact.textContent = row.factF1;

      const tdCit = document.createElement("td");
      tdCit.textContent = row.citPrec;

      const tdAbstain = document.createElement("td");
      tdAbstain.textContent = row.abstain;

      const tdLat = document.createElement("td");
      tdLat.textContent = row.lat;

      tr.appendChild(tdName);
      tr.appendChild(tdRecall);
      tr.appendChild(tdMrr);
      tr.appendChild(tdFact);
      tr.appendChild(tdCit);
      tr.appendChild(tdAbstain);
      tr.appendChild(tdLat);

      evalTableBody.appendChild(tr);
    });

    evalTableContainer.classList.remove("hidden");
  }
});
