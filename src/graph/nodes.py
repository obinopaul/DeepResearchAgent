# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Literal
from textwrap import dedent
from pydantic import ValidationError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from trustcall import create_extractor
from src.prompts.template import get_prompt_template
from langgraph.types import Command, interrupt
from functools import partial

from src.agents import create_agent, deep_agent
# from src.agents.deep_agents import DeepAgentState, create_deep_agent, async_create_deep_agent
from src.config.agents import AGENT_LLM_MAP
from src.config.configuration import Configuration
from src.llms.llm import get_llm_by_type, get_llm_token_limit_by_type
from src.prompts.planner_model import Plan
from src.prompts.template import apply_prompt_template
from src.tools import (
    crawl_tool,
    get_retriever_tool,
    get_web_search_tool,
    python_repl_tool,
)
from src.tools.search import LoggedTavilySearch
from src.utils.json_utils import repair_json_output
from src.utils.context_manager import ContextManager

from ..config import SELECTED_SEARCH_ENGINE, SearchEngine
from .types import State

logger = logging.getLogger(__name__)


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "The topic of the research task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return



def background_investigation_node(state: State, config: RunnableConfig):
    logger.info("background investigation node is running.")
    configurable = Configuration.from_runnable_config(config)
    query = state.get("research_topic")
    background_investigation_results = None
    if SELECTED_SEARCH_ENGINE == SearchEngine.TAVILY.value:
        searched_content = LoggedTavilySearch(
            max_results=configurable.max_search_results
        ).invoke(query)
        # check if the searched_content is a tuple, then we need to unpack it
        if isinstance(searched_content, tuple):
            searched_content = searched_content[0]
        if isinstance(searched_content, list):
            background_investigation_results = [
                f"## {elem['title']}\n\n{elem['content']}" for elem in searched_content
            ]
            return {
                "background_investigation_results": "\n\n".join(
                    background_investigation_results
                )
            }
        else:
            logger.error(
                f"Tavily search returned malformed response: {searched_content}"
            )
    else:
        background_investigation_results = get_web_search_tool(
            configurable.max_search_results
        ).invoke(query)
    return {
        "background_investigation_results": json.dumps(
            background_investigation_results, ensure_ascii=False
        )
    }


def build_plan_with_trustcall(messages: list[dict], config: RunnableConfig, existing: Plan | None = None) -> Plan:
    configurable = Configuration.from_runnable_config(config)
    logger.info("Building plan with TrustCall")
    
    if configurable.enable_deep_thinking:
        llm = get_llm_by_type("reasoning")
    elif AGENT_LLM_MAP["planner"] == "basic":
        llm = get_llm_by_type("basic")
    else:
        llm = get_llm_by_type(AGENT_LLM_MAP["planner"])
    extractor = create_extractor(
        llm,
        tools=[Plan],         # TrustCall will validate against Plan
        tool_choice="Plan",   # force Plan tool
        # enable_inserts not needed here (single doc)
    )

    kwargs = {"messages": messages}
    if existing is not None:
        kwargs["existing"] = {"Plan": existing.model_dump()}  # patch against current state

    result = extractor.invoke(kwargs)
    plan_obj = result["responses"][0]  # This is a validated Pydantic Plan instance
    return plan_obj



def planner_node(
    state: State, config: RunnableConfig
) -> Command[Literal["human_feedback", "reporter"]]:
    """Planner node that generate the full plan."""
    logger.info("Planner generating full plan")
    configurable = Configuration.from_runnable_config(config)
    
    # 1. Iteration Check: Prevent infinite loops by enforcing a maximum number of planning attempts.
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    if plan_iterations >= configurable.max_plan_iterations:
        logger.info(
            "Planner reached max iterations (%s). Using available plan to continue if possible.",
            configurable.max_plan_iterations,
        )
        existing_plan = state.get("current_plan")
        has_pending_plan = False
        if isinstance(existing_plan, Plan):
            has_pending_plan = bool(existing_plan.steps)
        elif isinstance(existing_plan, dict):
            has_pending_plan = bool(existing_plan.get("steps"))

        goto_target = "research_team" if has_pending_plan else "reporter"
        return Command(goto=goto_target)

    # 2. Message Preparation: Assemble the prompt with all necessary context.
    messages = apply_prompt_template("planner", state, configurable)
    if state.get("enable_background_investigation") and state.get(
        "background_investigation_results"
    ):
        messages += [
            {
                "role": "user",
                "content": (
                    "background investigation results of user query:\n"
                    + state["background_investigation_results"]
                    + "\n"
                ),
            }
        ]


    # 3. Handle Existing Plan: Safely validate and prepare the current plan for refinement.
    existing_plan = state.get("current_plan")
    if isinstance(existing_plan, dict):
        try:
            # Attempt to load a dictionary state into a Pydantic model
            existing_plan = Plan.model_validate(existing_plan)
        except ValidationError as e:
            logger.warning(f"Could not validate existing plan from dict: {e}. Proceeding without it.")
            existing_plan = None
    elif not isinstance(existing_plan, Plan):
        # Ensure we are only working with a valid Plan object or None
        existing_plan = None

    # 4. Core Logic & Error Handling: Execute the planning call within a try-except block.
    plan_has_steps = False
    try:
        new_plan: Plan = build_plan_with_trustcall(messages, config, existing=existing_plan)
        plan_has_steps = bool(new_plan.steps)
        if plan_has_steps and getattr(new_plan, "has_enough_context", False):
            logger.info(
                "Generated plan includes actionable steps; overriding has_enough_context to False to ensure deep research."
            )
            new_plan = new_plan.model_copy(update={"has_enough_context": False})

        full_response_content = new_plan.model_dump_json(indent=2)
        logger.info("Successfully generated and validated a new plan.")
        logger.debug(f"Planner response: {full_response_content}")

    except Exception as e:
        logger.exception(f"A critical error occurred during plan generation: {e}")
        # If this is the first attempt, end the process. Otherwise, route to the
        # reporter to present the last successful state before the error.
        goto = "reporter" if plan_iterations > 0 else "__end__"
        return Command(goto=goto)
    
    # 5. Context-Aware Routing: Decide the next step based on the LLM's assessment.
    # This check is sourced directly from your original implementation.
    # It assumes the `Plan` model has a boolean field `has_enough_context`.
    auto_accept_plan = bool(state.get("auto_accepted_plan", False))
    if plan_has_steps:
        goto = "research_team" if auto_accept_plan else "human_feedback"
        logger.info(
            "Planner prepared %d step(s). Routing to %s.",
            len(new_plan.steps),
            goto,
        )
    elif getattr(new_plan, "has_enough_context", False):
        logger.info("Planner determined it has enough context without steps. Routing to reporter.")
        goto = "reporter"
    else:
        logger.info("Planner requires additional information but no steps were produced. Routing for human feedback.")
        goto = "human_feedback"

    # 6. Update State: Commit the new plan and increment the iteration counter.
    return Command(
        update={
            "messages": [AIMessage(content=full_response_content, name="planner")],
            "current_plan": new_plan,  # Always store the validated Pydantic object
            "plan_iterations": plan_iterations + 1,
        },
        goto=goto,
    )



# def planner_node(
#     state: State, config: RunnableConfig
# ) -> Command[Literal["human_feedback", "reporter"]]:
#     """Planner node that generate the full plan."""
#     logger.info("Planner generating full plan")
#     configurable = Configuration.from_runnable_config(config)
#     plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
#     messages = apply_prompt_template("planner", state, configurable)

#     if state.get("enable_background_investigation") and state.get(
#         "background_investigation_results"
#     ):
#         messages += [
#             {
#                 "role": "user",
#                 "content": (
#                     "background investigation results of user query:\n"
#                     + state["background_investigation_results"]
#                     + "\n"
#                 ),
#             }
#         ]

#     if configurable.enable_deep_thinking:
#         llm = get_llm_by_type("reasoning")
#     elif AGENT_LLM_MAP["planner"] == "basic":
#         llm = get_llm_by_type("basic").with_structured_output(
#             Plan,
#             method="json_mode",
#         )
#     else:
#         llm = get_llm_by_type(AGENT_LLM_MAP["planner"])

#     # if the plan iterations is greater than the max plan iterations, return the reporter node
#     if plan_iterations >= configurable.max_plan_iterations:
#         return Command(goto="reporter")

#     full_response = ""
#     if AGENT_LLM_MAP["planner"] == "basic" and not configurable.enable_deep_thinking:
#         response = llm.invoke(messages)
#         full_response = response.model_dump_json(indent=4, exclude_none=True)
#     else:
#         response = llm.stream(messages)
#         for chunk in response:
#             full_response += chunk.content
#     logger.debug(f"Current state messages: {state['messages']}")
#     logger.info(f"Planner response: {full_response}")

#     try:
#         curr_plan = json.loads(repair_json_output(full_response))
#     except json.JSONDecodeError:
#         logger.warning("Planner response is not a valid JSON")
        # if plan_iterations > 0:
        #     return Command(goto="reporter")
        # else:
        #     return Command(goto="__end__")
#     if isinstance(curr_plan, dict) and curr_plan.get("has_enough_context"):
#         logger.info("Planner response has enough context.")
#         new_plan = Plan.model_validate(curr_plan)
#         return Command(
#             update={
#                 "messages": [AIMessage(content=full_response, name="planner")],
#                 "current_plan": new_plan,
#             },
#             goto="reporter",
#         )
#     return Command(
#         update={
#             "messages": [AIMessage(content=full_response, name="planner")],
#             "current_plan": full_response,
#         },
#         goto="human_feedback",
#     )


def human_feedback_node(
    state,
) -> Command[Literal["planner", "research_team", "reporter", "__end__"]]:
    current_plan = state.get("current_plan", "")
    # check if the plan is auto accepted
    auto_accepted_plan = state.get("auto_accepted_plan", False)
    if not auto_accepted_plan:
        feedback = interrupt("Please Review the Plan.")

        # if the feedback is not accepted, return the planner node
        if feedback and str(feedback).upper().startswith("[EDIT_PLAN]"):
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=feedback, name="feedback"),
                    ],
                },
                goto="planner",
            )
        elif feedback and str(feedback).upper().startswith("[ACCEPTED]"):
            logger.info("Plan is accepted by user.")
        else:
            raise TypeError(f"Interrupt value of {feedback} is not supported.")

    # if the plan is accepted, run the following node
    plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
    goto = "research_team"
    try:
        # Since current_plan is now a Pydantic object, we no longer need to parse it.
        # We just need to validate that it is the correct type.
        if not isinstance(current_plan, Plan):
            # If it's not a Plan object, raise an error to trigger the except block,
            # preserving your original error-handling flow.
            raise TypeError("current_plan is not a valid Plan object.")
        
        # increment the plan iterations (Your original logic)
        # plan_iterations += 1
        
        # The final return statement expects a dictionary, so we convert the object.
        # This replaces the old `json.loads(current_plan)`.
        new_plan = current_plan.model_dump()
    except (json.JSONDecodeError, TypeError): # Broadened to catch our new TypeError
        logger.warning("Planner response is not a valid JSON or Plan object")
        if plan_iterations > 1:  # the plan_iterations is increased before this check
            return Command(goto="reporter")
        else:
            return Command(goto="__end__")

    return Command(
        update={
            "current_plan": Plan.model_validate(new_plan),
            "plan_iterations": plan_iterations,
            "locale": new_plan["locale"],
        },
        goto=goto,
    )


# def human_feedback_node(
#     state,
# ) -> Command[Literal["planner", "research_team", "reporter", "__end__"]]:
#     current_plan = state.get("current_plan", "")
#     # check if the plan is auto accepted
#     auto_accepted_plan = state.get("auto_accepted_plan", False)
#     if not auto_accepted_plan:
#         feedback = interrupt("Please Review the Plan.")

#         # if the feedback is not accepted, return the planner node
#         if feedback and str(feedback).upper().startswith("[EDIT_PLAN]"):
#             return Command(
#                 update={
#                     "messages": [
#                         HumanMessage(content=feedback, name="feedback"),
#                     ],
#                 },
#                 goto="planner",
#             )
#         elif feedback and str(feedback).upper().startswith("[ACCEPTED]"):
#             logger.info("Plan is accepted by user.")
#         else:
#             raise TypeError(f"Interrupt value of {feedback} is not supported.")

#     # if the plan is accepted, run the following node
#     plan_iterations = state["plan_iterations"] if state.get("plan_iterations", 0) else 0
#     goto = "research_team"
#     try:
#         current_plan = repair_json_output(current_plan)
#         # increment the plan iterations
#         plan_iterations += 1
#         # parse the plan
#         new_plan = json.loads(current_plan)
#     except json.JSONDecodeError:
#         logger.warning("Planner response is not a valid JSON")
#         if plan_iterations > 1:  # the plan_iterations is increased before this check
#             return Command(goto="reporter")
#         else:
#             return Command(goto="__end__")

#     return Command(
#         update={
#             "current_plan": Plan.model_validate(new_plan),
#             "plan_iterations": plan_iterations,
#             "locale": new_plan["locale"],
#         },
#         goto=goto,
#     )


def coordinator_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "background_investigator", "__end__"]]:
    """Coordinator node that communicate with customers."""
    logger.info("Coordinator talking.")
    configurable = Configuration.from_runnable_config(config)
    messages = apply_prompt_template("coordinator", state)
    response = (
        get_llm_by_type(AGENT_LLM_MAP["coordinator"])
        .bind_tools([handoff_to_planner])
        .invoke(messages)
    )
    logger.debug(f"Current state messages: {state['messages']}")

    goto = "__end__"
    locale = state.get("locale", "en-US")  # Default locale if not specified
    research_topic = state.get("research_topic", "")

    if len(response.tool_calls) > 0:
        goto = "planner"
        if state.get("enable_background_investigation"):
            # if the search_before_planning is True, add the web search tool to the planner agent
            goto = "background_investigator"
        try:
            for tool_call in response.tool_calls:
                if tool_call.get("name", "") != "handoff_to_planner":
                    continue
                if tool_call.get("args", {}).get("locale") and tool_call.get(
                    "args", {}
                ).get("research_topic"):
                    locale = tool_call.get("args", {}).get("locale")
                    research_topic = tool_call.get("args", {}).get("research_topic")
                    break
        except Exception as e:
            logger.error(f"Error processing tool calls: {e}")
    else:
        logger.warning(
            "Coordinator response contains no tool calls. Terminating workflow execution."
        )
        logger.debug(f"Coordinator response: {response}")
    messages = state.get("messages", [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="coordinator"))
    return Command(
        update={
            "messages": messages,
            "locale": locale,
            "research_topic": research_topic,
            "resources": configurable.resources,
        },
        goto=goto,
    )


def reporter_node(state: State, config: RunnableConfig):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    configurable = Configuration.from_runnable_config(config)

    researcher_reports = state.get("researcher_reports", "")
    if isinstance(researcher_reports, str) and researcher_reports.strip():
        logger.info("Reporter received researcher reports; returning them as final report.")
        return {
            "final_report": researcher_reports,
            "researcher_reports": "",
        }

    current_plan = state.get("current_plan")
    input_ = {
        "messages": [
            HumanMessage(
                f"# Research Requirements\n\n## Task\n\n{current_plan.title}\n\n## Description\n\n{current_plan.thought}"
            )
        ],
        "locale": state.get("locale", "en-US"),
    }
    invoke_messages = apply_prompt_template("reporter", input_, configurable)
    observations = state.get("observations", [])

    # Add a reminder about the new report format, citation style, and table usage
    invoke_messages.append(
        HumanMessage(
            content="IMPORTANT: Structure your report according to the format in the prompt. Remember to include:\n\n1. Key Points - A bulleted list of the most important findings\n2. Overview - A brief introduction to the topic\n3. Detailed Analysis - Organized into logical sections\n4. Survey Note (optional) - For more comprehensive reports\n5. Key Citations - List all references at the end\n\nFor citations, DO NOT include inline citations in the text. Instead, place all citations in the 'Key Citations' section at the end using the format: `- [Source Title](URL)`. Include an empty line between each citation for better readability.\n\nPRIORITIZE USING MARKDOWN TABLES for data presentation and comparison. Use tables whenever presenting comparative data, statistics, features, or options. Structure tables with clear headers and aligned columns. Example table format:\n\n| Feature | Description | Pros | Cons |\n|---------|-------------|------|------|\n| Feature 1 | Description 1 | Pros 1 | Cons 1 |\n| Feature 2 | Description 2 | Pros 2 | Cons 2 |",
            name="system",
        )
    )

    observation_messages = []
    for observation in observations:
        observation_messages.append(
            HumanMessage(
                content=f"Below are some observations for the research task:\n\n{observation}",
                name="observation",
            )
        )

    # Context compression
    llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP["reporter"])
    compressed_state = ContextManager(llm_token_limit).compress_messages(
        {"messages": observation_messages}
    )
    invoke_messages += compressed_state.get("messages", [])

    logger.debug(f"Current invoke messages: {invoke_messages}")
    response = get_llm_by_type(AGENT_LLM_MAP["reporter"]).invoke(invoke_messages)
    response_content = response.content
    logger.info(f"reporter response: {response_content}")

    return {"final_report": response_content}


def research_team_node(state: State):
    """Research team node that collaborates on tasks."""
    logger.info("Research team is collaborating on tasks.")
    pass


def _extract_primary_user_brief(messages: list) -> str:
    """Return the most recent end-user HumanMessage content."""
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            name = getattr(message, "name", None)
            if name in (None, "user"):
                return message.content or ""
    return ""


def _render_plan_summary(plan: Plan, *, max_step_detail: int = 600) -> str:
    """Render the planner output into markdown-friendly text."""
    if plan is None:
        return "No plan information available."

    lines: list[str] = []
    lines.append(f"## Plan Title\n\n{plan.title}")
    if getattr(plan, "thought", None):
        lines.append("## Planner Rationale\n")
        lines.append(plan.thought)
    lines.append("## Plan Metadata\n")
    lines.append(f"- Locale: {plan.locale}")
    lines.append(f"- Has enough context: {plan.has_enough_context}")

    if plan.steps:
        lines.append("\n## Planned Steps\n")
        for idx, step in enumerate(plan.steps, start=1):
            lines.append(f"### Step {idx}: {step.title}")
            lines.append(step.description)
            lines.append(f"- Step type: {step.step_type}")
            lines.append(f"- Requires search: {step.need_search}")
            if step.execution_res:
                detail = step.execution_res.strip()
                if max_step_detail and len(detail) > max_step_detail:
                    detail = detail[: max_step_detail - 3] + "..."
                lines.append(f"- Existing execution result: {detail}")
            lines.append("")
    else:
        lines.append("\n(No steps were generated in the plan.)")

    return "\n".join(
        filter(None, [segment.strip() for segment in lines if segment is not None])
    ).strip()


def _extract_final_report_from_result(result: dict | Any) -> tuple[str, bool]:
    """Safely extract final report content from deep agent result."""
    response_content: str | None = None
    has_payload = False

    def _matches_final_report(name: str | None) -> bool:
        if not isinstance(name, str):
            return False
        try:
            return Path(name).name == "final_report.md"
        except Exception:
            return name == "final_report.md"

    def _extract_file_payload(file_entry):
        if isinstance(file_entry, str):
            stripped = file_entry.strip()
            return stripped or None
        if isinstance(file_entry, dict):
            for field in ("content", "data", "text", "value"):
                value = file_entry.get(field)
                if isinstance(value, str) and value.strip():
                    return value
        return None

    try:
        if isinstance(result, dict):
            files_obj = result.get("files")

            if isinstance(files_obj, dict):
                for file_name, file_entry in files_obj.items():
                    if _matches_final_report(file_name):
                        candidate = _extract_file_payload(file_entry)
                        if candidate:
                            response_content = candidate
                            has_payload = True
                            break
                if response_content is None:
                    maybe_direct = files_obj.get("final_report")
                    candidate = _extract_file_payload(maybe_direct)
                    if candidate:
                        response_content = candidate
                        has_payload = True

            elif isinstance(files_obj, list):
                for item in files_obj:
                    if isinstance(item, dict) and _matches_final_report(item.get("name")):
                        candidate = _extract_file_payload(item)
                        if candidate:
                            response_content = candidate
                            has_payload = True
                            break

            if response_content is None:
                raw_final_report = result.get("final_report")
                candidate = _extract_file_payload(raw_final_report)
                if candidate:
                    response_content = candidate
                    has_payload = True

            if (
                response_content is None
                and isinstance(result.get("messages"), list)
                and result["messages"]
            ):
                last = result["messages"][-1]
                try:
                    content_attr = getattr(last, "content", None)
                    if isinstance(content_attr, str):
                        stripped = content_attr.strip()
                        if stripped:
                            response_content = stripped
                            has_payload = True
                except Exception:
                    pass

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to parse deep agent result; falling back to string: %s", exc
        )
        response_content = str(result)
    finally:
        if response_content is None:
            response_content = str(result) if not isinstance(result, str) else result

    return response_content, has_payload





async def _execute_deepagent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team", "__end__"]]:
    """Execute the full research brief with the deep agent in a single run."""
    current_plan = state.get("current_plan")
    if current_plan is None:
        logger.warning("No current plan present; skipping deep agent execution.")
        return Command(goto="planner")

    locale_value = state.get("locale") or getattr(current_plan, "locale", "en-US")
    user_brief = _extract_primary_user_brief(state.get("messages", []))
    if user_brief and len(user_brief) > 6000:
        user_brief = user_brief[:6000] + "\n\n...[truncated]"
    plan_summary = _render_plan_summary(current_plan)

    brief_sections = [
        "# Original Research Brief",
        user_brief.strip() if user_brief else "(No direct user message captured in state.)",
        "# Planner Output Snapshot",
        plan_summary,
        "# Execution Instructions",
        dedent(
            f"""
            - Integrate the planner steps into your internal TODO list using the `write_todos` tool.
            - Expand or refine the steps as needed to ensure exhaustive coverage of the research brief.
            - Conduct thorough, tool-driven research before drafting any findings.
            - Store the original question in `question.txt`, and write the final deliverable to `final_report.md`.
            - Ensure the final report respects the locale `{locale_value}` and follows all citation requirements.
            """
        ).strip(),
    ]

    primary_message_content = "\n\n".join(
        [section for section in brief_sections if section]
    ).strip()
    messages = [HumanMessage(content=primary_message_content)]

    resources = state.get("resources")
    if resources:
        resources_lines = ["**The user mentioned the following resource files:**", ""]
        for resource in resources:
            resources_lines.append(f"- {resource.title} ({resource.description})")
        resources_lines.append(
            "\nYou MUST use the **local_search_tool** to retrieve the information from the resource files."
        )
        messages.append(HumanMessage(content="\n".join(resources_lines)))

    messages.append(
        HumanMessage(
            content="IMPORTANT: Track all sources and include a References section at the end using link reference format. Include an empty line between each citation.",
            name="system",
        )
    )

    logger.info("Executing consolidated deep_agent run for %s.", agent_name)
    logger.debug("Deep agent input messages: %s", primary_message_content)
    result = await agent.ainvoke(input={"messages": messages})

    response_content, has_final_report_payload = _extract_final_report_from_result(result)
    response_content = response_content.strip()
    logger.debug(
        "%s consolidated response (extracted): %s",
        agent_name.capitalize(),
        response_content,
    )

    observations = state.get("observations", []) or []
    if response_content:
        observations = [*observations, response_content]

    # Mark all plan steps as completed so downstream routing progresses.
    for step in getattr(current_plan, "steps", []) or []:
        step.execution_res = (
            step.execution_res
            or "Completed during consolidated deep-agent execution. Refer to final_report.md for detailed findings."
        )

    update_payload: dict[str, Any] = {
        "messages": [
            HumanMessage(
                content=response_content
                or "Completed consolidated deep-agent execution.",
                name=agent_name,
            )
        ],
        "observations": observations,
        "current_plan": current_plan,
        "step_attempts": {},
    }

    if agent_name == "researcher":
        if response_content:
            update_payload["researcher_reports"] = response_content
            if has_final_report_payload:
                update_payload["final_report"] = response_content
            else:
                update_payload["final_report"] = state.get(
                    "final_report", response_content
                )
        else:
            update_payload["researcher_reports"] = state.get(
                "researcher_reports", ""
            )
            update_payload["final_report"] = state.get("final_report", "")
    else:
        update_payload["researcher_reports"] = state.get("researcher_reports", "")
        update_payload["final_report"] = state.get("final_report", "")

    return Command(update=update_payload, goto="research_team")



async def _execute_agent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team"]]:
    """Helper function to execute a step using the specified agent."""
    current_plan = state.get("current_plan")
    plan_title = current_plan.title
    observations = state.get("observations", [])

    # Find the first unexecuted step
    current_step = None
    completed_steps = []
    for step in current_plan.steps:
        if not step.execution_res:
            current_step = step
            break
        else:
            completed_steps.append(step)

    if not current_step:
        logger.warning("No unexecuted step found")
        return Command(goto="research_team")

    logger.info(f"Executing step: {current_step.title}, agent: {agent_name}")

    # Safety guard: per-step attempts cap
    step_attempts = state.get("step_attempts", {}) or {}
    title_key = str(current_step.title)
    try:
        max_attempts = int(os.getenv("RESEARCH_STEP_MAX_ATTEMPTS", "3"))
        if max_attempts <= 0:
            max_attempts = 3
    except Exception:
        max_attempts = 3
    attempts = int(step_attempts.get(title_key, 0))
    if attempts >= max_attempts:
        logger.warning(
            f"Max attempts reached for step '{title_key}' ({attempts} >= {max_attempts}). Routing to planner."
        )
        return Command(
            update={
                "step_attempts": step_attempts,
                "current_plan": current_plan,
            },
            goto="planner",
        )

    # Format completed steps information
    completed_steps_info = ""
    if completed_steps:
        completed_steps_info = "# Completed Research Steps\n\n"
        for i, step in enumerate(completed_steps):
            completed_steps_info += f"## Completed Step {i + 1}: {step.title}\n\n"
            completed_steps_info += f"<finding>\n{step.execution_res}\n</finding>\n\n"

    # Prepare the input for the agent with completed steps info
    agent_input = {
        "messages": [
            HumanMessage(
                content=f"# Research Topic\n\n{plan_title}\n\n{completed_steps_info}# Current Step\n\n## Title\n\n{current_step.title}\n\n## Description\n\n{current_step.description}\n\n## Locale\n\n{state.get('locale', 'en-US')}"
            )
        ]
    }

    # Add citation reminder for researcher agent
    if agent_name == "researcher":
        if state.get("resources"):
            resources_info = "**The user mentioned the following resource files:**\n\n"
            for resource in state.get("resources"):
                resources_info += f"- {resource.title} ({resource.description})\n"

            agent_input["messages"].append(
                HumanMessage(
                    content=resources_info
                    + "\n\n"
                    + "You MUST use the **local_search_tool** to retrieve the information from the resource files.",
                )
            )

        agent_input["messages"].append(
            HumanMessage(
                content="IMPORTANT: DO NOT include inline citations in the text. Instead, track all sources and include a References section at the end using link reference format. Include an empty line between each citation for better readability. Use this format for each reference:\n- [Source Title](URL)\n\n- [Another Source](URL)",
                name="system",
            )
        )

    # Invoke the agent
    default_recursion_limit = 25
    try:
        env_value_str = os.getenv("AGENT_RECURSION_LIMIT", str(default_recursion_limit))
        parsed_limit = int(env_value_str)

        if parsed_limit > 0:
            recursion_limit = parsed_limit
            logger.info(f"Recursion limit set to: {recursion_limit}")
        else:
            logger.warning(
                f"AGENT_RECURSION_LIMIT value '{env_value_str}' (parsed as {parsed_limit}) is not positive. "
                f"Using default value {default_recursion_limit}."
            )
            recursion_limit = default_recursion_limit
    except ValueError:
        raw_env_value = os.getenv("AGENT_RECURSION_LIMIT")
        logger.warning(
            f"Invalid AGENT_RECURSION_LIMIT value: '{raw_env_value}'. "
            f"Using default value {default_recursion_limit}."
        )
        recursion_limit = default_recursion_limit

    logger.info(f"Agent input: {agent_input}")
    # Increment attempt before invoking
    step_attempts[title_key] = attempts + 1
    result = await agent.ainvoke(
        input=agent_input, config={"recursion_limit": recursion_limit}
    )

    # Process the result
    response_content = result["messages"][-1].content
    logger.debug(f"{agent_name.capitalize()} full response: {response_content}")

    # Update the step with the execution result
    current_step.execution_res = response_content
    logger.info(f"Step '{current_step.title}' execution completed by {agent_name}")

    # Clear attempts for this step now that it is completed
    if title_key in step_attempts:
        try:
            del step_attempts[title_key]
        except Exception:
            pass

    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response_content,
                    name=agent_name,
                )
            ],
            "observations": observations + [response_content],
            "step_attempts": step_attempts,
            # Persist the updated plan so routing logic sees completed steps
            "current_plan": current_plan,
        },
        goto="research_team",
    )


async def _setup_and_execute_agent_step(
    state: State,
    config: RunnableConfig,
    agent_type: str,
    default_tools: list,
) -> Command[Literal["research_team"]]:
    """Helper function to set up an agent with appropriate tools and execute a step.

    This function handles the common logic for both researcher_node and coder_node:
    1. Configures MCP servers and tools based on agent type
    2. Creates an agent with the appropriate tools or uses the default agent
    3. Executes the agent on the current step

    Args:
        state: The current state
        config: The runnable config
        agent_type: The type of agent ("researcher" or "coder")
        default_tools: The default tools to add to the agent

    Returns:
        Command to update state and go to research_team
    """
    configurable = Configuration.from_runnable_config(config)
    mcp_servers = {}
    enabled_tools = {}
    main_prompt = get_prompt_template("main_research_prompt")
    sub_research_prompt = get_prompt_template("sub_research_prompt")
    sub_critique_prompt = get_prompt_template("sub_critique_prompt")
    sub_query_optimizer_prompt = get_prompt_template("sub_query_optimizer_prompt")
    sub_insight_extractor_prompt = get_prompt_template("sub_insight_extractor_prompt")
    sub_followup_prompt = get_prompt_template("sub_followup_prompt")
    sub_evidence_auditor_prompt = get_prompt_template("sub_evidence_auditor_prompt")
    main_prompt = get_prompt_template("main_research_prompt")
    sub_research_prompt = get_prompt_template("sub_research_prompt")
    sub_critique_prompt = get_prompt_template("sub_critique_prompt")
    sub_query_optimizer_prompt = get_prompt_template("sub_query_optimizer_prompt")
    sub_insight_extractor_prompt = get_prompt_template("sub_insight_extractor_prompt")
    sub_followup_prompt = get_prompt_template("sub_followup_prompt")
    sub_evidence_auditor_prompt = get_prompt_template("sub_evidence_auditor_prompt")

    main_prompt = get_prompt_template("main_research_prompt")
    sub_research_prompt = get_prompt_template("sub_research_prompt")
    sub_critique_prompt = get_prompt_template("sub_critique_prompt")
    sub_query_optimizer_prompt = get_prompt_template("sub_query_optimizer_prompt")
    sub_insight_extractor_prompt = get_prompt_template("sub_insight_extractor_prompt")
    sub_followup_prompt = get_prompt_template("sub_followup_prompt")
    sub_evidence_auditor_prompt = get_prompt_template("sub_evidence_auditor_prompt")

    main_prompt = get_prompt_template("main_research_prompt")
    sub_research_prompt = get_prompt_template("sub_research_prompt")
    sub_critique_prompt = get_prompt_template("sub_critique_prompt")
    sub_query_optimizer_prompt = get_prompt_template("sub_query_optimizer_prompt")
    sub_insight_extractor_prompt = get_prompt_template("sub_insight_extractor_prompt")
    sub_followup_prompt = get_prompt_template("sub_followup_prompt")
    sub_evidence_auditor_prompt = get_prompt_template("sub_evidence_auditor_prompt")

    # Extract MCP server configuration for this agent type
    if configurable.mcp_settings:
        for server_name, server_config in configurable.mcp_settings["servers"].items():
            if (
                server_config["enabled_tools"]
                and agent_type in server_config["add_to_agents"]
            ):
                mcp_servers[server_name] = {
                    k: v
                    for k, v in server_config.items()
                    if k in ("transport", "command", "args", "url", "env", "headers")
                }
                for tool_name in server_config["enabled_tools"]:
                    enabled_tools[tool_name] = server_name

    # Create and execute agent with MCP tools if available
    if mcp_servers:
        client = MultiServerMCPClient(mcp_servers)
        loaded_tools = default_tools[:]
        all_tools = await client.get_tools()
        for tool in all_tools:
            if tool.name in enabled_tools:
                tool.description = (
                    f"Powered by '{enabled_tools[tool.name]}'.\n{tool.description}"
                )
                loaded_tools.append(tool)

        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP["deepagent"])
        raw_limit = llm_token_limit or 60000
        context_budget = max(raw_limit // 20, 4000)
        context_budget = min(context_budget, max(raw_limit - 8000, 4000))
        pre_model_hook = partial(ContextManager(context_budget, 3).compress_messages)
        agent = create_agent(
            agent_type, agent_type, loaded_tools, agent_type, pre_model_hook
        )
        return await _execute_agent_step(state, agent, agent_type)
    else:
        # Use default tools if no MCP servers are configured
        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP["deepagent"])
        raw_limit = llm_token_limit or 60000
        context_budget = max(raw_limit // 20, 4000)
        context_budget = min(context_budget, max(raw_limit - 8000, 4000))
        pre_model_hook = partial(ContextManager(context_budget, 3).compress_messages)
        agent = create_agent(
            agent_type, agent_type, default_tools, agent_type, pre_model_hook
        )
        return await _execute_agent_step(state, agent, agent_type)



async def _setup_and_execute_deep_agent_step(
    state: State,
    config: RunnableConfig,
    agent_type: str,
    default_tools: list,
) -> Command[Literal["research_team", "__end__"]]:
    """Helper function to set up an agent with appropriate tools and execute a step.

    This function handles the common logic for both researcher_node and coder_node:
    1. Configures MCP servers and tools based on agent type
    2. Creates an agent with the appropriate tools or uses the default agent
    3. Executes the agent on the current step

    Args:
        state: The current state
        config: The runnable config
        agent_type: The type of agent ("researcher" or "coder")
        default_tools: The default tools to add to the agent

    Returns:
        Command to update state and go to research_team or end
    """
    configurable = Configuration.from_runnable_config(config)
    mcp_servers = {}
    enabled_tools = {}
    main_prompt = get_prompt_template("main_research_prompt")
    sub_research_prompt = get_prompt_template("sub_research_prompt")
    sub_critique_prompt = get_prompt_template("sub_critique_prompt")
    sub_query_optimizer_prompt = get_prompt_template("sub_query_optimizer_prompt")
    sub_insight_extractor_prompt = get_prompt_template("sub_insight_extractor_prompt")
    sub_followup_prompt = get_prompt_template("sub_followup_prompt")
    sub_evidence_auditor_prompt = get_prompt_template("sub_evidence_auditor_prompt")

    # Extract MCP server configuration for this agent type
    if configurable.mcp_settings:
        for server_name, server_config in configurable.mcp_settings["servers"].items():
            if (
                server_config["enabled_tools"]
                and agent_type in server_config["add_to_agents"]
            ):
                mcp_servers[server_name] = {
                    k: v
                    for k, v in server_config.items()
                    if k in ("transport", "command", "args", "url", "env", "headers")
                }
                for tool_name in server_config["enabled_tools"]:
                    enabled_tools[tool_name] = server_name

    # Create and execute agent with MCP tools if available
    if mcp_servers:
        client = MultiServerMCPClient(mcp_servers)
        loaded_tools = default_tools[:]
        all_tools = await client.get_tools()
        for tool in all_tools:
            if tool.name in enabled_tools:
                tool.description = (
                    f"Powered by '{enabled_tools[tool.name]}'.\n{tool.description}"
                )
                loaded_tools.append(tool)

        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
        context_budget = min(max(llm_token_limit or 0, 20000), 60000)
        pre_model_hook = partial(ContextManager(context_budget, 3).compress_messages)
        
        # agent = create_agent(
        #     agent_type, agent_type, loaded_tools, agent_type, pre_model_hook
        # ) 
        agent = deep_agent(
            agent_name=agent_type,
            agent_type=agent_type,
            tools = loaded_tools,
            prompt_template = main_prompt,
            sub_research_prompt = sub_research_prompt,
            sub_critique_prompt = sub_critique_prompt,
            sub_query_optimizer_prompt = sub_query_optimizer_prompt,
            sub_insight_extractor_prompt = sub_insight_extractor_prompt,
            sub_followup_prompt = sub_followup_prompt,
            sub_evidence_auditor_prompt = sub_evidence_auditor_prompt,
            pre_model_hook = pre_model_hook
        )


        return await _execute_deepagent_step(state, agent, agent_type)
    else:
        # Use default tools if no MCP servers are configured
        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
        context_budget = min(max(llm_token_limit or 0, 20000), 60000)
        pre_model_hook = partial(ContextManager(context_budget, 3).compress_messages)
        loaded_tools = default_tools[:] # This is the line to add
        # agent = create_agent(
        #     agent_type, agent_type, default_tools, agent_type, pre_model_hook
        # )
        
        agent = deep_agent(
            agent_name=agent_type,
            agent_type=agent_type,
            tools = loaded_tools,
            prompt_template = main_prompt,
            sub_research_prompt = sub_research_prompt,
            sub_critique_prompt = sub_critique_prompt,
            sub_query_optimizer_prompt = sub_query_optimizer_prompt,
            sub_insight_extractor_prompt = sub_insight_extractor_prompt,
            sub_followup_prompt = sub_followup_prompt,
            sub_evidence_auditor_prompt = sub_evidence_auditor_prompt,
            pre_model_hook = pre_model_hook
        )

        return await _execute_deepagent_step(state, agent, agent_type)


async def researcher_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team", "__end__"]]:
    """Researcher node that do research"""
    logger.info("Researcher node is researching.")
    configurable = Configuration.from_runnable_config(config)

    if not hasattr(crawl_tool, "name"):
        # Assign a readable fallback name
        setattr(crawl_tool, "name", getattr(crawl_tool, "__name__", f"crawl_tool"))

    tools = [get_web_search_tool(configurable.max_search_results), crawl_tool]
    retriever_tool = get_retriever_tool(state.get("resources", []))
    if retriever_tool:
        tools.insert(0, retriever_tool)
        
    # Ensure every tool has a `name` attribute
    for i, tool in enumerate(tools):
        if not hasattr(tool, "name"):
            # Assign a readable fallback name
            setattr(tool, "name", getattr(tool, "__name__", f"unnamed_tool_{i}"))

    logger.info(f"Researcher tools: {[tool.name for tool in tools]}")
    
    # return await _setup_and_execute_agent_step(
    #     state,
    #     config,
    #     "researcher",
    #     tools,
    # )
    
    return await _setup_and_execute_deep_agent_step(
        state,
        config,
        "researcher",
        tools,
    )


async def coder_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Coder node that do code analysis."""
    logger.info("Coder node is coding.")
    return await _setup_and_execute_agent_step(
        state,
        config,
        "coder",
        [python_repl_tool],
    )
