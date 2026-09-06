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

  let activeEvalPollInterval = null;

  // Character counter for query textarea
  queryInput.addEventListener("input", () => {
    const len = queryInput.value.length;
    charCounter.textContent = `${len} / 2000`;
  });

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
      if (mData.counters) {
        metricQueries.textContent = String(mData.counters.query_requests_total || 0);
        metricEvals.textContent = String(mData.counters.evaluation_jobs_total || 0);
      }
      if (mData.gauges && mData.gauges.avg_query_latency_ms !== undefined) {
        metricLatency.textContent = `${Math.round(mData.gauges.avg_query_latency_ms)}ms`;
      }
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

    const payload = {
      query: query,
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
        answerStatusTag.textContent = "Error";
        answerPlaceholder.classList.remove("hidden");
        answerPlaceholder.textContent = `Error (${resp.status}): ${errorMsg}`;
        answerText.classList.add("hidden");
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
        citations.forEach((cit) => {
          const card = document.createElement("div");
          card.className = "citation-card";

          const header = document.createElement("div");
          header.className = "citation-header";

          const title = document.createElement("span");
          title.className = "citation-title";
          title.textContent = cit.title || "Untitled Source";

          const source = document.createElement("span");
          source.className = "citation-source";
          source.textContent = cit.chunk_id ? `Chunk: ${cit.chunk_id}` : cit.source_uri;

          header.appendChild(title);
          header.appendChild(source);

          const excerpt = document.createElement("div");
          excerpt.className = "citation-excerpt";
          excerpt.textContent = cit.excerpt;

          card.appendChild(header);
          card.appendChild(excerpt);
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

        startPollingEvaluation(data.evaluation_id);
      } else {
        evalStatusBadge.className = "badge badge-danger";
        evalStatusBadge.textContent = "Rejected";
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
          runEvalBtn.disabled = false;
          evalSpinner.classList.add("hidden");
          loadSystemHealth();
        } else if (job.status === "failed") {
          clearInterval(activeEvalPollInterval);
          evalStatusBadge.className = "badge badge-danger";
          evalJobMessage.textContent = `Job failed: ${job.safe_message || "Unknown error"}`;
          runEvalBtn.disabled = false;
          evalSpinner.classList.add("hidden");
          loadSystemHealth();
        }
      } catch (err) {
        // Continue polling on transient failure
      }
    }, 2000);
  }
});
