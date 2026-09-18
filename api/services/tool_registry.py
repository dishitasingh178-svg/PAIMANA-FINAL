from api.services.assistant_tools import (
    search_projects,
    get_project,
    get_latest_prediction,
    get_project_updates,
    get_project_alerts,
    get_risk_history,
    get_portfolio_risk_summary,
    get_critical_projects,
    get_sector_analytics,
    get_state_analytics,
    get_risk_trends,
)


TOOL_REGISTRY = {

    "search_projects": {
        "function": search_projects,
        "description": (
            "Search PAIMANA projects by project name, sector, "
            "implementing agency, or state."
        ),
    },

    "get_project": {
        "function": get_project,
        "description": (
            "Get complete basic information about a specific "
            "PAIMANA project using its project ID."
        ),
    },

    "get_latest_prediction": {
        "function": get_latest_prediction,
        "description": (
            "Get the latest stored ML prediction and risk information "
            "for a specific PAIMANA project."
        ),
    },

    "get_project_updates": {
        "function": get_project_updates,
        "description": (
            "Get recent monthly progress updates for a specific "
            "PAIMANA project."
        ),
    },

    "get_project_alerts": {
        "function": get_project_alerts,
        "description": (
            "Get alerts generated for a specific PAIMANA project. "
            "Can optionally return only unresolved alerts."
        ),
    },

    "get_risk_history": {
        "function": get_risk_history,
        "description": (
            "Get historical ML risk predictions for a specific "
            "PAIMANA project."
        ),
    },

    "get_portfolio_risk_summary": {
        "function": get_portfolio_risk_summary,
        "description": (
            "Get an overall summary of the latest risk predictions "
            "across the PAIMANA project portfolio."
        ),
    },

    "get_critical_projects": {
        "function": get_critical_projects,
        "description": (
            "Get projects whose latest stored prediction is classified "
            "as critical risk."
        ),
    },

    "get_sector_analytics": {
        "function": get_sector_analytics,
        "description": (
            "Get project risk statistics grouped by infrastructure sector."
        ),
    },

    "get_state_analytics": {
        "function": get_state_analytics,
        "description": (
            "Get project risk statistics grouped by state."
        ),
    },

    "get_risk_trends": {
        "function": get_risk_trends,
        "description": (
            "Get historical portfolio-level risk trends by reporting month."
        ),
    },
}


# -------------------------------------------------------------
# Tool lookup
# -------------------------------------------------------------

def get_tool(tool_name: str):
    """
    Return a registered tool by name.
    """
    return TOOL_REGISTRY.get(tool_name)


# -------------------------------------------------------------
# Human-readable tool list
# -------------------------------------------------------------

def list_tools():
    """
    Return the names and descriptions of all available tools.
    """

    return [
        {
            "name": name,
            "description": tool["description"],
        }
        for name, tool in TOOL_REGISTRY.items()
    ]


# -------------------------------------------------------------
# LLM Tool Schemas
# -------------------------------------------------------------

LLM_TOOL_SCHEMAS = [
    {
        "name": "search_projects",
        "description": (
            "Search PAIMANA projects by project name, sector, "
            "implementing agency, or state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search text describing the project, sector, "
                        "implementing agency, or state."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of projects to return.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },

    {
        "name": "get_project",
        "description": (
            "Get complete basic information about a specific "
            "PAIMANA project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The PAIMANA project ID.",
                },
            },
            "required": ["project_id"],
        },
    },

    {
        "name": "get_latest_prediction",
        "description": (
            "Get the latest stored ML prediction and risk information "
            "for a specific PAIMANA project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The PAIMANA project ID.",
                },
            },
            "required": ["project_id"],
        },
    },

    {
        "name": "get_project_updates",
        "description": (
            "Get recent monthly progress updates for a specific "
            "PAIMANA project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The PAIMANA project ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of updates to return.",
                    "default": 12,
                },
            },
            "required": ["project_id"],
        },
    },

    {
        "name": "get_project_alerts",
        "description": (
            "Get alerts generated for a specific PAIMANA project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The PAIMANA project ID.",
                },
                "unresolved_only": {
                    "type": "boolean",
                    "description": (
                        "If true, return only unresolved alerts."
                    ),
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of alerts to return.",
                    "default": 20,
                },
            },
            "required": ["project_id"],
        },
    },

    {
        "name": "get_risk_history",
        "description": (
            "Get historical ML risk predictions for a specific "
            "PAIMANA project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The PAIMANA project ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of historical predictions."
                    ),
                    "default": 12,
                },
            },
            "required": ["project_id"],
        },
    },

    {
        "name": "get_portfolio_risk_summary",
        "description": (
            "Get an overall summary of the latest risk predictions "
            "across the PAIMANA project portfolio."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    {
        "name": "get_critical_projects",
        "description": (
            "Get projects whose latest stored prediction is classified "
            "as critical risk."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of critical projects to return."
                    ),
                    "default": 10,
                },
            },
            "required": [],
        },
    },

    {
        "name": "get_sector_analytics",
        "description": (
            "Get project risk statistics grouped by "
            "infrastructure sector."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    {
        "name": "get_state_analytics",
        "description": (
            "Get project risk statistics grouped by state."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    {
        "name": "get_risk_trends",
        "description": (
            "Get historical portfolio-level risk trends "
            "by reporting month."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of reporting periods to return."
                    ),
                    "default": 12,
                },
            },
            "required": [],
        },
    },
]


def get_llm_tool_schemas():
    """
    Return tool definitions in a format that can be supplied
    to an LLM provider's tool/function-calling interface.
    """

    return LLM_TOOL_SCHEMAS