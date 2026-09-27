import inspect
import json
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from api.services.tool_registry import (
    TOOL_REGISTRY,
    get_llm_tool_schemas,
)


load_dotenv()


SYSTEM_PROMPT = """
You are the PAIMANA AI Assistant.

PAIMANA is an infrastructure project monitoring and predictive analytics
system.

Your job is to answer users using PAIMANA's actual project data and tools.

IMPORTANT RULES:

1. Use PAIMANA tools whenever the user asks about projects, risks,
   predictions, alerts, sectors, states, trends, costs, delays,
   or other PAIMANA database information.

2. Do not invent project information.

3. Do not invent risk scores, probabilities, costs, dates, delays,
   predictions, or alerts.

4. If PAIMANA tools return no data, clearly tell the user that the
   requested data is currently unavailable in the PAIMANA database.

5. You may explain what a PAIMANA metric means using general knowledge,
   but do not present general knowledge as actual PAIMANA data.

6. When a tool provides numerical information, preserve the meaning
   and units of those numbers.

7. Keep answers clear and useful for government officials, analysts,
   project managers, and public users.

8. If the user asks about a particular project, first identify the
   project using the available PAIMANA tools.

9. If multiple tools are needed to answer a question, use them.

10. Do not claim that you performed an action if you only retrieved
    information.

11. If the question is unrelated to PAIMANA, you may answer briefly
    using general knowledge, while making clear that the answer is
    not based on PAIMANA project data.

12. Never fabricate missing PAIMANA data.

13. PAIMANA's database is the source of truth for project-specific
    information.

14. Use the conversation history to understand references such as
    "it", "that project", "the first one", "those projects", and
    "what about its risk".

15. Conversation history provides context only. For actual PAIMANA
    facts, always use PAIMANA tools.

16. Do not assume that a project mentioned in conversation still has
    the same current risk. Query the database when current information
    is requested.

17. Once sufficient tool information is available, answer the user's
    question directly instead of repeatedly calling unrelated tools.

18. Only call tools whose exact names are provided in the available tool
    definitions. Never invent, guess, rename, or substitute a tool name.
    If no available tool can provide the requested information, say that
    the requested data is currently unavailable rather than attempting
    to call a nonexistent tool.

19. Tool selection guide (use these exact tools):
    - Current early warnings, alerts or warning signals across the
      portfolio, or the highest-risk / critical projects:
      get_critical_projects, plus get_portfolio_risk_summary for the
      number of projects in each risk tier.
    - Early-warning alerts for one specific project: find its project_id
      with search_projects (unless it is already known), then call
      get_project_alerts with that project_id.
    - A project's current risk: get_latest_prediction. Its risk over time:
      get_risk_history. Its monthly reported figures: get_project_updates.
    - Portfolio totals: get_portfolio_risk_summary. Sector or state
      comparisons: get_sector_analytics / get_state_analytics. Portfolio
      risk over time: get_risk_trends.
    - There is no portfolio-wide alert-listing tool; do not invent one.
"""


class LLMService:

    def __init__(
        self,
        tool_registry=None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.tool_registry = tool_registry or TOOL_REGISTRY

        self.api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
        )

        self.model = (
            model
            or os.getenv(
                "GEMINI_MODEL",
                "gemini-3.5-flash-lite",
            )
        )

        self.client = None

        if self.api_key:
            self.client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=45000),
            )

    # =========================================================
    # CONFIGURATION
    # =========================================================

    def is_configured(self) -> bool:
        return (
            self.client is not None
            and bool(self.api_key)
        )

    # =========================================================
    # SYSTEM PROMPT
    # =========================================================

    def build_system_prompt(self) -> str:
        return (
            SYSTEM_PROMPT
            + "\nAvailable tools (exact names): "
            + ", ".join(self.get_available_tools())
            + "\n"
        )

    def _unknown_tool_error(self, tool_name: str) -> str:
        return (
            f"Tool '{tool_name}' is not available. "
            f"Available tools: {', '.join(self.get_available_tools())}."
        )

    # =========================================================
    # AVAILABLE TOOLS
    # =========================================================

    def get_available_tools(self):
        return list(self.tool_registry.keys())

    # =========================================================
    # GEMINI TOOL SCHEMAS
    # =========================================================

    def _get_tool_schemas(self):
        return get_llm_tool_schemas()

    def get_gemini_tools(self):
        declarations = []

        for schema in self._get_tool_schemas():

            declaration = types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters=schema.get("parameters"),
            )

            declarations.append(declaration)

        return [
            types.Tool(
                function_declarations=declarations
            )
        ]

    # =========================================================
    # CONTEXT
    # =========================================================

    def prepare_context(
        self,
        user_query: str,
        tool_results: Optional[list] = None,
        conversation_history: Optional[list] = None,
    ) -> Dict[str, Any]:

        return {
            "user_query": user_query,
            "tool_results": tool_results or [],
            "conversation_history": (
                conversation_history or []
            ),
        }

    # =========================================================
    # TOOL RESULT FORMATTING
    # =========================================================

    def format_tool_result(
        self,
        tool_name: str,
        result: Any,
    ) -> str:

        payload = {
            "tool": tool_name,
            "result": result,
        }

        return json.dumps(
            payload,
            default=str,
            ensure_ascii=False,
            indent=2,
        )

    # =========================================================
    # SAFE TOOL EXECUTION
    # =========================================================

    def execute_tool(
        self,
        tool_name: str,
        db,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        arguments = arguments or {}

        if tool_name not in self.tool_registry:

            return {
                "success": False,
                "tool": tool_name,
                "error": self._unknown_tool_error(tool_name),
            }

        tool_entry = self.tool_registry[tool_name]

        if isinstance(tool_entry, dict):
            function = tool_entry.get("function")
        else:
            function = tool_entry

        if not callable(function):

            return {
                "success": False,
                "tool": tool_name,
                "error": (
                    f"Tool '{tool_name}' is not callable."
                ),
            }

        try:

            signature = inspect.signature(function)

            parameters = signature.parameters

            allowed_arguments = {
                name
                for name in parameters
                if name != "db"
            }

            unknown_arguments = (
                set(arguments.keys())
                - allowed_arguments
            )

            if unknown_arguments:

                return {
                    "success": False,
                    "tool": tool_name,
                    "error": (
                        "Unknown tool arguments: "
                        + ", ".join(
                            sorted(unknown_arguments)
                        )
                    ),
                }

            result = function(
                db,
                **arguments,
            )

            return {
                "success": True,
                "tool": tool_name,
                "result": result,
            }

        except Exception as exc:

            return {
                "success": False,
                "tool": tool_name,
                "error": str(exc),
            }

    # =========================================================
    # CONVERSATION HISTORY
    # =========================================================

    def _add_conversation_history(
        self,
        contents: list,
        conversation_history: Optional[list],
    ):

        if not conversation_history:
            return

        for message in conversation_history:

            if not isinstance(message, dict):
                continue

            role = str(
                message.get("role", "")
            ).strip().lower()

            content = str(
                message.get("content", "")
            ).strip()

            if not content:
                continue

            if role == "user":

                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=content
                            )
                        ],
                    )
                )

            elif role == "assistant":

                contents.append(
                    types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text=content
                            )
                        ],
                    )
                )

    # =========================================================
    # FINAL ANSWER FROM COLLECTED TOOL RESULTS
    # =========================================================

    def _generate_final_answer(
        self,
        user_query: str,
        tool_calls_log: list,
        conversation_history: Optional[list] = None,
    ) -> str:

        tool_context = json.dumps(
            tool_calls_log,
            default=str,
            ensure_ascii=False,
            indent=2,
        )

        history_context = json.dumps(
            conversation_history or [],
            default=str,
            ensure_ascii=False,
            indent=2,
        )

        final_prompt = f"""
Answer the user's PAIMANA question using ONLY the tool results
provided below for PAIMANA-specific facts.

Do not call any tools.

If the tool results show that there are no projects or no data,
say that clearly.

Do not invent missing information.

Conversation history:
{history_context}

Current user question:
{user_query}

Tool results:
{tool_context}

Now provide the final answer directly to the user.
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=final_prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.build_system_prompt(),
                temperature=0.2,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL,
                ),
            ),
        )

        return response.text or (
            "The PAIMANA tools returned the available information, "
            "but I could not generate a final response."
        )

    # =========================================================
    # GEMINI RESPONSE GENERATION
    # =========================================================

    def generate_response(
        self,
        user_query: str,
        db,
        conversation_history: Optional[list] = None,
        max_tool_rounds: int = 3,
    ):

        if not self.is_configured():

            return {
                "success": False,
                "answer": (
                    "Gemini assistant is not configured."
                ),
                "error": (
                    "GEMINI_API_KEY is missing."
                ),
                "tool_calls": [],
            }

        tool_calls_log = []
        rejected_tool_calls = []

        try:

            # -------------------------------------------------
            # Build Gemini tools
            # -------------------------------------------------

            gemini_tools = self.get_gemini_tools()

            # -------------------------------------------------
            # Build conversation
            # -------------------------------------------------

            contents = []

            self._add_conversation_history(
                contents=contents,
                conversation_history=conversation_history,
            )

            # -------------------------------------------------
            # Current user question
            # -------------------------------------------------

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=user_query
                        )
                    ],
                )
            )

            # =================================================
            # TOOL-CALLING LOOP
            # =================================================

            for round_number in range(max_tool_rounds):

                print(
                    f"[LLM] Gemini round "
                    f"{round_number + 1}/"
                    f"{max_tool_rounds}"
                )

                response = (
                    self.client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=(
                                self.build_system_prompt()
                            ),
                            tools=gemini_tools if round_number == 0 else None,
                            temperature=0.2,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=types.ThinkingLevel.MINIMAL,
                            ),
                        ),
                    )
                )

                function_calls = response.function_calls

                # -------------------------------------------------
                # Final answer
                # -------------------------------------------------

                if not function_calls:

                    answer = response.text or ""

                    return {
                        "success": True,
                        "answer": answer,
                        "tool_calls": tool_calls_log,
                        "rejected_tool_calls": rejected_tool_calls,
                    }

                # -------------------------------------------------
                # Preserve Gemini model response
                # -------------------------------------------------

                if response.candidates:

                    model_content = (
                        response.candidates[0].content
                    )

                    if model_content:

                        contents.append(
                            model_content
                        )

                # -------------------------------------------------
                # Execute tools
                # -------------------------------------------------

                # Only registered tools may run. Names the model invents
                # (e.g. when later rounds carry no tool declarations) are
                # rejected here, before anything executes.
                valid_calls = []

                for function_call in function_calls:

                    if function_call.name in self.tool_registry:
                        valid_calls.append(function_call)
                        continue

                    print(
                        f"[LLM] Rejected unknown tool: "
                        f"{function_call.name}"
                    )

                    rejected_tool_calls.append(
                        {
                            "tool": function_call.name,
                            "arguments": dict(function_call.args or {}),
                            "error": self._unknown_tool_error(
                                function_call.name
                            ),
                        }
                    )

                function_response_parts = []

                for function_call in valid_calls:

                    tool_name = function_call.name

                    tool_arguments = dict(
                        function_call.args or {}
                    )

                    print(
                        f"[LLM] Calling tool: "
                        f"{tool_name}"
                    )

                    print(
                        f"[LLM] Arguments: "
                        f"{tool_arguments}"
                    )

                    tool_result = self.execute_tool(
                        tool_name=tool_name,
                        db=db,
                        arguments=tool_arguments,
                    )

                    print(
                        f"[LLM] Tool result: "
                        f"{tool_result}"
                    )

                    tool_calls_log.append(
                        {
                            "tool": tool_name,
                            "arguments": tool_arguments,
                            "result": tool_result,
                        }
                    )

                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={
                                "result": tool_result
                            },
                        )
                    )

                # An invented tool means the model has run out of useful
                # tool calls: stop here and answer from the valid results
                # instead of spending further rounds on guesses.
                if rejected_tool_calls:

                    print(
                        "[LLM] Unknown tool requested; answering from "
                        "valid tool results."
                    )

                    return self._answer_from_collected_results(
                        user_query=user_query,
                        tool_calls_log=tool_calls_log,
                        rejected_tool_calls=rejected_tool_calls,
                        conversation_history=conversation_history,
                    )

                # -------------------------------------------------
                # Send function results back
                # -------------------------------------------------

                contents.append(
                    types.Content(
                        role="user",
                        parts=function_response_parts,
                    )
                )

            # =================================================
            # MAX TOOL ROUNDS
            # =================================================
            #
            # Instead of returning an error, use all collected
            # tool results to generate a final answer WITHOUT
            # giving Gemini access to tools.
            #
            # This prevents unnecessary tool loops.
            # =================================================

            print(
                "[LLM] Maximum tool rounds reached."
            )

            return self._answer_from_collected_results(
                user_query=user_query,
                tool_calls_log=tool_calls_log,
                rejected_tool_calls=rejected_tool_calls,
                conversation_history=conversation_history,
            )

        except Exception as exc:

            return {
                "success": False,
                "answer": (
                    "I could not connect to the "
                    "Gemini assistant right now."
                ),
                "error": str(exc),
                "tool_calls": tool_calls_log,
                "rejected_tool_calls": rejected_tool_calls,
            }

    def _answer_from_collected_results(
        self,
        user_query: str,
        tool_calls_log: list,
        rejected_tool_calls: list,
        conversation_history: Optional[list] = None,
    ):
        """
        Final answer from the tool results already collected, with no tools
        offered (so no further tool calls can be requested).
        """

        print(
            "[LLM] Generating final answer "
            "from collected tool results."
        )

        final_answer = self._generate_final_answer(
            user_query=user_query,
            tool_calls_log=tool_calls_log,
            conversation_history=conversation_history,
        )

        return {
            "success": True,
            "answer": final_answer,
            "tool_calls": tool_calls_log,
            "rejected_tool_calls": rejected_tool_calls,
        }

    # =========================================================
    # SERIALIZATION
    # =========================================================

    def serialize_context(
        self,
        context: Dict[str, Any],
    ) -> str:

        return json.dumps(
            context,
            default=str,
            ensure_ascii=False,
            indent=2,
        )