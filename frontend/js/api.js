const API_BASE_URL = `${window.location.origin}/api/v1`;

async function fetchAPI(endpoint, options = {}) {
  const config = { ...options, headers: { ...(options.headers || {}) } };
  if (config.body && !config.headers["Content-Type"]) config.headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE_URL}${endpoint}`, config);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `HTTP Error ${res.status}`);
  }
  return res.json();
}

const API = {
  getDashboardStats: () => fetchAPI("/dashboard/summary"),
  getHighRiskMapProjects: () => fetchAPI("/dashboard/ongoing-high-risk"),
  getRiskDistribution: () => fetchAPI("/dashboard/risk-distribution"),
  getAlerts: (filters = {}) => fetchAPI(`/alerts?${new URLSearchParams(filters)}`),
  getWarningWorkspace: (filters = {}) => fetchAPI(`/alerts/workspace?${new URLSearchParams(filters)}`, {cache:'no-store', signal:AbortSignal.timeout(15000)}),
  getAlertCases: (filters = {}) => fetchAPI(`/alerts/cases?${new URLSearchParams(filters)}`, {cache:'no-store'}),
  updateProjectAlertStatus: (projectId, status, reviewNote) => fetchAPI(`/alerts/projects/${encodeURIComponent(projectId)}/status`, {
    method:'PATCH', body:JSON.stringify({status, ...(reviewNote === undefined ? {} : {review_note:reviewNote})})
  }),
  getPriorityAlerts: (limit = 10) => fetchAPI(`/alerts/priority?limit=${limit}`, {cache:'no-store'}),
  getAlertSummary: () => fetchAPI("/alerts/summary", {cache:'no-store'}),
  updateAlertStatus: (alertId, status, reviewNote) => fetchAPI(`/alerts/${encodeURIComponent(alertId)}/status`, {
    method: "PATCH", body: JSON.stringify({status, ...(reviewNote === undefined ? {} : {review_note: reviewNote})})
  }),
  getProjects: (search = "") => fetchAPI(`/projects${search ? `?q=${encodeURIComponent(search)}` : ""}`),
  getProjectById: (id) => fetchAPI(`/projects/${encodeURIComponent(id)}`),
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
      console.log(`[PAIMANA job ${jobId.slice(0, 8)}] ${event.type}${event.stage ? ` · ${event.stage}` : ""}: ${event.message || ""}`, event);
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

window.fetchAPI = fetchAPI;
window.API = API;
async function fetchDashboardStats() { return API.getDashboardStats(); }
