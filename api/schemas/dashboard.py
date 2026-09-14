from pydantic import BaseModel
from typing import List

# Matches fetchDashboardStats() in assets/js/api.js
class DashboardSummaryResponse(BaseModel):
    total_projects: int
    high_risk_count: int
    delayed_count: int
    original_cost_lakh_cr: str
    revised_cost_lakh_cr: str
    expenditure_lakh_cr: str

# Matches the Leaflet marker data expected by loadOngoingHighRiskProjects() in dashboard.html
class HighRiskProjectMapItem(BaseModel):
    project_id: str
    project_name: str
    status: str
    sector: str
    risk_score: float
    delay_months: int
    lat: float
    lng: float

# Matches the dataset array expected by Chart.js in loadRiskDistributionChart()
class RiskDistributionResponse(BaseModel):
    low: int
    watch: int
    elevated: int
    critical: int

# Matches the alert elements rendered in the dashboard feed
class AlertItem(BaseModel):
    project_name: str
    message: str
    severity: str  # "critical" or "high"