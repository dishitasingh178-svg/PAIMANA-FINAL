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
  getAlerts: () => fetchAPI("/dashboard/alerts"),
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
  runPrediction: (projectId, reportMonth = null) => fetchAPI("/predictions", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, ...(reportMonth ? { report_month: reportMonth } : {}) })
  }),
  askAssistant: (query) => fetchAPI("/assistant", { method: "POST", body: JSON.stringify({ query, voice: false }) })
};

window.fetchAPI = fetchAPI;
window.API = API;
async function fetchDashboardStats() { return API.getDashboardStats(); }
