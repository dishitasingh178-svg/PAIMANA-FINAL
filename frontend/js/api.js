const API_BASE_URL = `${window.location.origin}/api/v1`;
const API_DEFAULT_TIMEOUT_MS = 30000;

class ApiError extends Error {
  constructor(message, { status = 0, endpoint = "", cause } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.endpoint = endpoint;
    if (cause) this.cause = cause;
  }
}

function apiErrorMessage(errorData, status) {
  const detail = errorData && (errorData.detail ?? errorData.message);
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) return detail.map(d => d.msg || JSON.stringify(d)).join("; ");
  if (status === 404) return "The requested record was not found.";
  if (status >= 500) return "The PAIMANA server could not complete this request.";
  return `HTTP Error ${status}`;
}

// Identical GETs that are already in flight share one request.
const inflightGets = new Map();

// options: standard fetch options plus
//   timeout (ms, default 30s; 0 disables) and dedupe (GET only, default true).
// Pass options.signal to make a request cancellable (such requests are not shared).
async function fetchAPI(endpoint, options = {}) {
  const { timeout = API_DEFAULT_TIMEOUT_MS, dedupe = true, ...fetchOptions } = options;
  const config = { ...fetchOptions, headers: { ...(fetchOptions.headers || {}) } };
  if (config.body && !config.headers["Content-Type"]) config.headers["Content-Type"] = "application/json";
  const method = (config.method || "GET").toUpperCase();
  const url = `${API_BASE_URL}${endpoint}`;
  const shareable = method === "GET" && dedupe && !config.signal;

  if (shareable && inflightGets.has(url)) return inflightGets.get(url);

  const run = (async () => {
    const signals = [config.signal, timeout ? AbortSignal.timeout(timeout) : null].filter(Boolean);
    if (signals.length > 1 && AbortSignal.any) config.signal = AbortSignal.any(signals);
    else if (signals.length === 1) config.signal = signals[0];

    let res;
    try {
      res = await fetch(url, config);
    } catch (err) {
      if (err.name === "AbortError" && fetchOptions.signal?.aborted) throw err;  // caller cancelled
      if (err.name === "TimeoutError" || err.name === "AbortError") {
        throw new ApiError("The server took too long to respond. Please retry.", { endpoint, cause: err });
      }
      throw new ApiError("Cannot reach the PAIMANA server. Check your connection and retry.", { endpoint, cause: err });
    }
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new ApiError(apiErrorMessage(errorData, res.status), { status: res.status, endpoint });
    }
    return res.json();
  })();

  if (shareable) {
    inflightGets.set(url, run);
    run.finally(() => inflightGets.delete(url)).catch(() => {});
  }
  return run;
}

function apiQuery(params = {}) {
  const clean = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return clean.length ? `?${new URLSearchParams(clean)}` : "";
}

const API = {
  getDashboardStats: (options) => fetchAPI("/dashboard/summary", options),
  getHighRiskMapProjects: (options) => fetchAPI("/dashboard/ongoing-high-risk", options),
  getRiskDistribution: (options) => fetchAPI("/dashboard/risk-distribution", options),
  getDashboardAlerts: (options) => fetchAPI("/dashboard/alerts", options),
  getSectorBreakdown: (options) => fetchAPI("/dashboard/sector-breakdown", options),
  getSectorAnalytics: (options) => fetchAPI("/analytics/sectors", options),
  getStateAnalytics: (options) => fetchAPI("/analytics/states", options),
  getRiskTrends: (options) => fetchAPI("/analytics/trends", options),
  getStateSummary: (options) => fetchAPI("/analytics/state-summary", options),
  getAlerts: (filters = {}) => fetchAPI(`/alerts?${new URLSearchParams(filters)}`),
  // ~1 MB and 3–15 s under load, so it gets a longer timeout than the 30 s default would need for others.
  getWarningWorkspace: (filters = {}) => fetchAPI(`/alerts/workspace?${new URLSearchParams(filters)}`, {cache:'no-store', timeout:45000}),
  getAlertCases: (filters = {}) => fetchAPI(`/alerts/cases?${new URLSearchParams(filters)}`, {cache:'no-store'}),
  updateProjectAlertStatus: (projectId, status, reviewNote) => fetchAPI(`/alerts/projects/${encodeURIComponent(projectId)}/status`, {
    method:'PATCH', body:JSON.stringify({status, ...(reviewNote === undefined ? {} : {review_note:reviewNote})})
  }),
  getPriorityAlerts: (limit = 10) => fetchAPI(`/alerts/priority?limit=${limit}`, {cache:'no-store'}),
  getAlertSummary: () => fetchAPI("/alerts/summary", {cache:'no-store'}),
  updateAlertStatus: (alertId, status, reviewNote) => fetchAPI(`/alerts/${encodeURIComponent(alertId)}/status`, {
    method: "PATCH", body: JSON.stringify({status, ...(reviewNote === undefined ? {} : {review_note: reviewNote})})
  }),
  // getProjects("text") keeps the original search-only form; an object adds sector/status.
  getProjects: (search = "", options) => typeof search === "object" && search !== null
    ? fetchAPI(`/projects/${apiQuery(search)}`, options)
    : fetchAPI(`/projects${search ? `?q=${encodeURIComponent(search)}` : ""}`, options),
  getProjectById: (id, options) => fetchAPI(`/projects/${encodeURIComponent(id)}`, options),
  getProjectExplanation: (id, options) => fetchAPI(`/projects/${encodeURIComponent(id)}/explanation`, { timeout: 60000, ...options }),
  uploadProjectPDF: async (file) => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE_URL}/projects/upload-pdf`, {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail ||
        errorData.message ||
        `HTTP Error ${response.status}`
      );
    }

    return response.json();
  },
  getJob: (jobId) => fetchAPI(`/jobs/${encodeURIComponent(jobId)}`),
  // Follows a background job over SSE. handlers: onEvent(event), onDone(job), onError(error).
  // Returns a function that stops listening.
  streamJob: (jobId, { onEvent, onDone, onError } = {}) => {
    const url = `${API_BASE_URL}/jobs/${encodeURIComponent(jobId)}/events`;
    const events = new EventSource(url);
    let finished = false;

    const finish = async (failure) => {
      if (finished) return;
      finished = true;
      events.close();
      if (failure) { onError?.(failure); return; }
      try { onDone?.(await API.getJob(jobId)); } catch (err) { onError?.(err); }
    };

    events.onmessage = (message) => {
      let event;
      try { event = JSON.parse(message.data); } catch { return; }
      console.log(`${jobLogPrefix(event)} job ${jobId.slice(0, 8)} · ${event.type}: ${event.message || ""}`, event);
      onEvent?.(event);
      if (event.type === "job_completed" || event.type === "job_failed") finish();
    };

    // EventSource reconnects on its own (resuming from Last-Event-ID). Only give up
    // once the browser stops retrying, then check whether the job ended meanwhile.
    events.onerror = async () => {
      if (finished || events.readyState !== EventSource.CLOSED) return;
      try {
        const job = await API.getJob(jobId);
        if (job.status === "completed" || job.status === "failed") finish();
        else finish(new Error("Lost connection to the processing stream."));
      } catch (err) {
        finish(err);
      }
    };

    return () => { finished = true; events.close(); };
  },
  runPrediction: (projectId, reportMonth = null) => fetchAPI("/predictions", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, ...(reportMonth ? { report_month: reportMonth } : {}) })
  }),
  askAssistant: (query) => fetchAPI("/assistant", { method: "POST", body: JSON.stringify({ query, voice: false }) })
};

// Console trace labels for PDF job events (technical proof layer; no secrets logged).
function jobLogPrefix(event) {
  if (event.type === "job_failed") return "[PAIMANA] ✕";
  if (event.detail === "Transaction committed") return "[DATABASE]";
  return ({
    received: "[PDF]", validating: "[PDF]", extracting: "[EXTRACTOR]", normalizing: "[INGESTION]",
    ingesting: "[INGESTION]", predicting: "[ML]", alerting: "[ALERT ENGINE]", complete: "[PAIMANA]"
  })[event.stage] || "[PAIMANA]";
}

window.ApiError = ApiError;
window.fetchAPI = fetchAPI;
window.API = API;
async function fetchDashboardStats() { return API.getDashboardStats(); }
