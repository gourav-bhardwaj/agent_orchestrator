import os
import uuid
import logging
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
from agents import Agent, Runner, ModelSettings
from typing import Any, Literal, TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field
from agent_registry import StructuredResponse, TaskAgent, find, invoke_with_artifacts, invoke_with_artifacts_v1
from pathlib import Path
from langgraph.graph.state import CompiledStateGraph
import operator
from observability import span
import langfuse_config

from sqlalchemy.orm import Session, sessionmaker

from workflow_operations import Workflow, engine
from workflow_service import WorkflowService
from workflow_statistics_svc import WorkflowStatisticsService

from langfuse import observe
from metrics import (
    LLM_REQUESTS,
    LLM_COST,
    INPUT_TOKENS,
    OUTPUT_TOKENS,
    LLM_LATENCY,
    LLM_ERRORS
)

load_dotenv(override=True)
model = "gpt-4.1-mini"

SessionMaker = sessionmaker(
    bind=engine,
    class_=Session,
    expire_on_commit=False,
)

workflow_svc = WorkflowService(SessionMaker)
workflow_stats_svc = WorkflowStatisticsService(SessionMaker)

# 1. Base Configuration setup
logging.basicConfig(
    level=logging.INFO,                           # Set minimum severity level to log
    format='%(asctime)s - %(levelname)s - %(message)s', # Define log layout structure
    datefmt='%Y-%m-%d %H:%M:%S'                    # Style the timestamp output
)

# 2. Instantiate a module-level logger 
logger = logging.getLogger(__name__)

def record_statistics_safely(
    workflow_id: uuid.UUID,
    *,
    succeeded: bool,
) -> None:
    try:
        workflow_stats_svc.record_execution(
            workflow_id,
            succeeded=succeeded,
        )
    except SQLAlchemyError:
        logger.exception(
            "Unable to record workflow statistics for workflow %s",
            workflow_id,
        )

class Subtask(BaseModel):
    name: str = Field(
        description="Unique name of the subtask."
    )

    description: str = Field(
        description="Clear description of what the subtask must accomplish."
    )

    status: Literal["pending", "completed", "failed"] = Field(
        default="pending",
        description="Current status of the subtask."
    )

    execution_type: Literal["async", "sync"] = Field(
        default="sync",
        description="Whether the subtask should execute synchronously or asynchronously."
    )

    depends_on: list[str] = Field(
        default_factory=list,
        description="Names of subtasks that must complete before this subtask can execute."
    )

class PlannerOutput(BaseModel):
    subtasks: list[Subtask]

planner_agent = Agent(
    name="planner_agent",
    model=model,
    instructions="""You are a Planner Agent responsible for decomposing a user's request into a set of executable subtasks.

    Your job is ONLY to create a structured execution plan. Do not execute tools, do not answer the user's request directly, and do not invent results.

    You receive:
    1. The user's original query.
    2. Context describing the available agents, tools, capabilities, and constraints.

    Your output MUST be a JSON object containing a list of subtasks.

    Each subtask must contain exactly these fields:

    {
    "name": "unique_subtask_name",
    "description": "Clear description of what this subtask must accomplish",
    "status": "pending",
    "execution_type": "sync",
    "depends_on": []
    }

    Allowed values:

    status:
    - "pending"
    - "completed"
    - "failed"

    For a newly generated plan, status MUST always be "pending".

    execution_type:
    - "sync"
    - "async"

    Use "sync" when the subtask must be completed before dependent subtasks can continue.
    Use "async" when the subtask is independent of other currently planned subtasks and can safely execute concurrently.

    depends_on:
    - Contains the exact `name` values of subtasks that must be completed before this subtask can execute.
    - Use an empty list [] when there are no dependencies.
    - A subtask may depend on one or multiple subtasks.
    - Never reference a subtask that does not exist.
    - Dependencies must form a Directed Acyclic Graph (DAG).
    - NEVER create circular dependencies.

    ==================================================
    PLANNING PRINCIPLES
    ==================================================

    1. Understand the user's actual goal
    Break the user's request into meaningful executable steps.
    Do not split a simple operation unnecessarily.

    Bad:
    - Validate employee name
    - Validate employee email
    - Validate employee phone

    Better:
    - validate_employee_details

    2. Create atomic subtasks

    Each subtask should have one clear responsibility.
    A subtask should be independently understandable by an executor agent.

    Bad:
    "Handle employee onboarding"

    Better:
    "Create a new employee record using the provided employee details."

    3. Identify dependencies

    A subtask depends on another subtask when it requires the previous subtask's result.
    Example:

    A: get_department
    B: create_employee

    B depends on A because employee creation requires the department information.
    Therefore:

    {
    "name": "create_employee",
    "depends_on": ["get_department"]
    }

    4. Do not create unnecessary dependencies

    If two tasks do not depend on each other's results, they should NOT depend on each other.
    Example:

    A: notify_hr
    B: notify_it

    If both can execute independently:

    A depends_on []
    B depends_on []

    Both can potentially execute asynchronously.

    5. Use parallel execution whenever possible
    Independent subtasks should be marked:

    "execution_type": "async"

    Example:
    {
    "name": "notify_hr",
    "execution_type": "async",
    "depends_on": []
    }

    {
    "name": "notify_it",
    "execution_type": "async",
    "depends_on": []
    }

    6. Use sync for dependency chains

    If B requires the result of A:

    A -> B

    Then A should normally be:

    "execution_type": "sync"

    and B should depend on A.

    7. Preserve execution order through dependencies

    Do NOT use the array order as the source of truth for execution order.

    The `depends_on` field defines execution order.

    For example:

    A -> C
    B -> C

    means A and B can execute independently, while C must wait for both.

    8. Use meaningful and unique names

    Subtask names must:
    - be unique
    - be concise
    - use snake_case
    - describe the operation
    - be suitable for referencing from `depends_on`

    Good:
    - get_departments
    - validate_employee
    - create_employee
    - notify_hr

    Bad:
    - task1 
    - step2
    - process
    - do_it

    9. Do not duplicate work

    If the same information can be obtained by one subtask, do not create multiple subtasks that retrieve the same information.

    10. Do not invent capabilities

    Only create subtasks that can reasonably be performed using the provided context, agents, tools, or capabilities.

    If a required capability is unavailable, still describe the required subtask when it is necessary to represent the user's requested workflow, but clearly describe the requirement in the subtask.

    11. Keep subtasks executable

    The description must tell the executor what needs to be done.

    Bad:
    "Handle department"

    Good:
    "Retrieve the department matching the department name provided by the user and return its department ID."

    12. Handle conditional workflows

    When a later operation depends on a condition, represent the logical operation explicitly.

    Example:

    User:
    "Onboard John. If his department does not exist, create it first."

    Possible plan:

    get_department
    create_department
    create_employee

    However, if the planner cannot know whether the department exists before execution, describe the dependency appropriately and allow the executor/validator to determine the runtime condition.

    13. Avoid unnecessary decomposition

    Do not create a subtask for every sentence or individual field.

    The goal is an efficient execution plan, not a detailed explanation of the user's request.

    ==================================================
    DAG REQUIREMENTS
    ==================================================

    The generated plan MUST be a valid Directed Acyclic Graph.

    Before returning the final JSON, internally verify:

    - Every subtask name is unique.
    - Every dependency references an existing subtask.
    - No subtask depends on itself.
    - No circular dependency exists.
    - Independent tasks are not artificially chained.
    - Every dependent task has all required dependencies.
    - The graph contains at least one root node when subtasks exist.
    - The graph represents the logical execution flow of the user's request.

    Example DAG:

    A
    ├── B
    ├── C
    └── D
        └── E

    Represented as:

    A depends_on []
    B depends_on ["A"]
    C depends_on ["A"]
    D depends_on ["A"]
    E depends_on ["D"]

    B and C can potentially execute in parallel after A.

    ==================================================
    ASYNC VS SYNC
    ==================================================

    Choose execution_type based on dependency and task nature.

    Use "sync" when:
    - The task produces information required by another task.
    - The task is part of a sequential workflow.
    - The task modifies state and subsequent operations depend on its result.
    - Execution order matters.

    Use "async" when:
    - The task is independent.
    - The task can execute concurrently with other independent tasks.
    - The task does not need another subtask's output.
    - Parallel execution is safe.

    Do not mark every independent task as async merely because it has no dependencies. Use async when concurrent execution provides a meaningful benefit or is naturally appropriate.

    ==================================================
    EXAMPLES
    ==================================================

    Example 1:

    User query:
    "Get all employees from the engineering department."

    Plan:

    {
        "subtasks": [
            {
                "name": "get_engineering_department",
                "description": "Find the engineering department and return its department identifier.",
                "status": "pending",
                "execution_type": "sync",
                "depends_on": []
            },
            {
                "name": "get_department_employees",
                "description": "Retrieve all employees belonging to the engineering department using the department identifier returned by the previous subtask.",
                "status": "pending",
                "execution_type": "sync",
                "depends_on": ["get_engineering_department"]
            }
        ]
    }

    Example 2:

    User query:
    "Onboard John as a Java developer in the Engineering department and notify HR and IT."

    Plan:

    {
        "subtasks": [
            {
                "name": "get_engineering_department",
                "description": "Find the Engineering department and return its department identifier.",
                "status": "pending",
                "execution_type": "sync",
                "depends_on": []
            },
            {
                "name": "onboard_employee",
                "description": "Create John's employee record using his provided details, Java developer designation, and the Engineering department identifier.",
                "status": "pending",
                "execution_type": "sync",
                "depends_on": ["get_engineering_department"]
            },
            {
                "name": "notify_hr",
                "description": "Notify HR that John has been onboarded.",
                "status": "pending",
                "execution_type": "async",
                "depends_on": ["onboard_employee"]
            },
            {
                "name": "notify_it",
                "description": "Notify IT that John has been onboarded so the required IT onboarding activities can be initiated.",
                "status": "pending",
                "execution_type": "async",
                "depends_on": ["onboard_employee"]
            }
        ]
    }

    Example 3:

    User query:
    "Get employees and departments and send me a summary."

    Plan:

    {
        "subtasks": [
            {
                "name": "get_employees",
                "description": "Retrieve the relevant employee records required for the user's request.",
                "status": "pending",
                "execution_type": "async",
                "depends_on": []
            },
            {
                "name": "get_departments",
                "description": "Retrieve the relevant department records required for the user's request.",
                "status": "pending",
                "execution_type": "async",
                "depends_on": []
            },
            {
                "name": "generate_summary",
                "description": "Create a summary using the employee and department information returned by the previous subtasks.",
                "status": "pending",
                "execution_type": "sync",
                "depends_on": ["get_employees", "get_departments"]
            }
        ]
    }

    ==================================================
    OUTPUT FORMAT
    ==================================================

    Return ONLY valid JSON.

    Do not return:
    - Markdown
    - Code fences
    - Explanations
    - Comments
    - Additional fields
    - Natural language outside the JSON

    The top-level JSON object MUST have this structure:

    {
        "subtasks": [
            {
                "name": "string",
                "description": "string",
                "status": "pending",
                "execution_type": "sync",
                "depends_on": []
            }
        ]
    }
    """,
    output_type=PlannerOutput,
    model_settings=ModelSettings(temperature=0.8)
)

def merge_results(left: dict, right: dict) -> dict:
    return {**left, **right}

# class OrchestratorState(TypedDict):
#     user_query: str
#     tasks: dict[str, Subtask]
#     results: Annotated[dict, merge_results]

class OrchestratorState(TypedDict):
    user_query: str
    workflow_id: uuid.UUID
    tasks: dict[str, Subtask]
    results: Annotated[dict, merge_results]


# def create_executable_node(task: Subtask, agent_url: str):
#     async def executable_node(state: OrchestratorState):
#         print(f"Current subtask: {task.name}")
#         # valid_agent = False
#         # while not valid_agent:
#         #     task_agent = await find(task.description)
#         #     print(f"Agent `{task_agent}` for task: {task.description}")
#         #     decision = str(input("Enter agent valid or not [Y/N]:")).strip().lower()
#         #     valid_agent = True if decision in {"y", "yes"} else False

#         # updated_response = {}
#         # if not task_agent:
#         #     updated_response = {
#         #         "results": {
#         #             **state.get("results", {}),
#         #             task.name: StructuredResponse(
#         #                 message="Agent returned no response.",
#         #                 status="failure",
#         #             ),
#         #         }
#         #     }

#         # result = await invoke(agents[0], task.description, state["user_query"])
#         # async for result in invoke(
#         #     task_agent,
#         #     task.description,
#         #     state["user_query"],
#         # ):
#         #     updated_response = {
#         #         "results": {
#         #             **state.get("results", {}),
#         #             task.name: result,
#         #         }
#         #     }
#         task_agent = TaskAgent(task=task.description, agent_url=agent_url)
#         # result = await invoke(task_agent)
#         # return result
#         latest_result = None

#         # async for result in invoke_with_artifacts(task_agent):
#         async for result in invoke_with_artifacts_v1(task_agent):
#             print("Updated result:", result)
#             latest_result = result

#         return {
#             "results": {
#                 task.name: latest_result,
#             }
#         }
#     return executable_node

# def create_executable_node(task: Subtask, agent_url: str):
#     async def executable_node(state: OrchestratorState):
#         with span(
#             "execute_task",
#             task_name=task.name,
#             execution_type=task.execution_type,
#             agent_url=agent_url,
#         ):
#             task_agent = TaskAgent(
#                 task=task.description,
#                 agent_url=agent_url,
#             )

#             latest_result = None

#             async for result in invoke_with_artifacts_v1(task_agent):
#                 latest_result = result

#             return {
#                 "results": {
#                     task.name: latest_result,
#                 }
#             }
#     return executable_node

def create_executable_node(
    task: Subtask,
    agent_url: str,
    workflow_id: uuid.UUID,
):
    async def executable_node(state: OrchestratorState):
        with span(
            "execute_task",
            task_name=task.name,
            execution_type=task.execution_type,
            agent_url=agent_url,
        ):
            task_agent = TaskAgent(
                task=task.description,
                agent_url=agent_url,
            )

            latest_result = None

            try:
                async for result in invoke_with_artifacts_v1(task_agent):
                    latest_result = result

                record_statistics_safely(
                    workflow_id,
                    succeeded=True,
                )

                return {
                    "results": {
                        task.name: latest_result,
                    }
                }
            except Exception:
                record_statistics_safely(
                    workflow_id,
                    succeeded=False,
                )
                raise

    return executable_node

# async def generate_plan(query: str) -> PlannerOutput:
#     response = await Runner.run(
#         planner_agent,
#         input=query,
#         max_turns=3
#     )
#     return response.final_output

INPUT_PRICE = 0.40/1_000_000
OUTPUT_PRICE = 1.60/1_000_000

@observe(name="planner-agent-execution")
async def generate_plan(query: str) -> PlannerOutput:
    import time
    start_time = time.perf_counter()
    LLM_REQUESTS.labels(model=model, agent="planner_agent").inc()
    try:
        with span(
                "generate_plan",
                query_length=len(query),
                model=model,
            ) as current_span:
                response = await Runner.run(
                    planner_agent,
                    input=query,
                    max_turns=3,
                )
        
                current_span.set_attribute(
                    "plan.subtask_count",
                    len(response.final_output.subtasks),
                )
        
                answer = response.final_output
        
                # Access token usage
                usage = response.context_wrapper.usage
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens

                # Update Prometheus metrics
                INPUT_TOKENS.labels(model=model, agent="planner_agent").inc(input_tokens)
                OUTPUT_TOKENS.labels(model=model, agent="planner_agent").inc(output_tokens)

                generation_cost_usd = (input_tokens * INPUT_PRICE + output_tokens * OUTPUT_PRICE)
                LLM_COST.labels(model=model, agent="planner_agent").inc(generation_cost_usd)
        
                return answer
    except Exception:
        LLM_ERRORS.labels(model=model, agent="planner_agent").inc()
        raise
    finally:
        duration = time.perf_counter() - start_time
        LLM_LATENCY.labels(model=model, agent="planner_agent").observe(duration)

def build_graph(plan: PlannerOutput, agent_map: dict, workflow_id: uuid.UUID):
    builder = StateGraph(OrchestratorState)
    task_map = {task.name: task for task in plan.subtasks}

    # ----------- Validate the subtasks ---------------
    for task in plan.subtasks:
        for dep in task.depends_on:
            if dep not in task_map:
                raise ValueError(f"Subtask dependency `{dep}` not found!")

    # ----------- Add Node ----------------------------
    for task in plan.subtasks:
        builder.add_node(task.name, create_executable_node(task, agent_map[task.name], workflow_id))

    # ----------- Add First Node Edge With START --------------
    for task in plan.subtasks:
        if len(task.depends_on) == 0:
            builder.set_entry_point(task.name)

    # ----------- Set Edges With Another Node --------------
    for task in plan.subtasks:
        for dep in task.depends_on:
            builder.add_edge(dep, task.name)

    # ----------- Add Terminal Node Edge With END ------------
    terminal_nodes = [
        task.name
        for task in plan.subtasks
        if not any(
            task.name in other_task.depends_on
            for other_task in plan.subtasks
        )
    ]

    for terminal_node in terminal_nodes:
        builder.set_finish_point(terminal_node)

    return builder.compile()

# async def create_dag_pipeline(query: str):
#     plan = await create_plan(user_query=query, attempts=3)
#     task_agent_map = {}
#     for subtask in plan.subtasks:
#         agent_url = await agent_selection(task=subtask)
#         task_agent_map[subtask.name] = agent_url
#     dag = await generate_dag(plan, task_agent_map)
#     result = await dag.ainvoke({
#         "user_query": query
#     })
#     print("Final plan has been ready!")
#     print(result)

async def create_dag_pipeline(
    query: str,
    status_id: int,
    created_by: str = "ADMIN",
):
    plan = await create_plan(
        user_query=query,
        attempts=3,
    )

    task_agent_map: dict[str, str] = {}

    for subtask in plan.subtasks:
        agent_url = await agent_selection(task=subtask)
        task_agent_map[subtask.name] = agent_url

    workflow_id = uuid.uuid4()

    dag, image_path = await generate_dag_with_image(
        plan,
        task_agent_map,
        workflow_id,
    )

    workflow = Workflow(
        id=workflow_id,
        name=query[:200],
        description=query,
        graph_image_url=str(image_path),
        status_id=status_id,
        created_by=created_by,
    )

    try:
        saved_workflow = workflow_svc.save_workflow(workflow)
    except SQLAlchemyError:
        logger.exception(
            "Unable to persist workflow %s; continuing graph execution",
            workflow_id,
        )
        saved_workflow = None

    if saved_workflow:
        try:
            workflow_stats_svc.save_statistics(
                workflow_id=workflow_id,
            )
        except SQLAlchemyError:
            logger.exception(
                "Unable to initialize statistics for workflow %s; continuing graph execution",
                workflow_id,
            )

    result = await dag.ainvoke(
        {
            "user_query": query,
            "workflow_id": saved_workflow.id,
            "tasks": {
                task.name: task
                for task in plan.subtasks
            },
            "results": {},
        }
    )

    print("Final plan has been ready!")
    print(result)

    return {
        "workflow": saved_workflow,
        "result": result,
    }

async def agent_selection(task: Subtask):
    print(f"Current subtask: {task.name}")
    valid_agent = False
    task_agent = {}
    while not valid_agent:
        task_agent = await find(task.description)
        print(f"Agent `{task_agent}` for task: {task.description}")
        decision = str(input("Enter agent valid or not [Y/N]:")).strip().lower()
        valid_agent = True if decision in {"y", "yes"} else False
    return task_agent.agent_url

async def generate_dag(plan: PlannerOutput, task_agent_map: dict, workflow_id: uuid.UUID) -> CompiledStateGraph:
    dag = build_graph(plan, task_agent_map, workflow_id)
    png_data = dag.get_graph().draw_mermaid_png()
    Path(f"dag_{str(uuid.uuid4())}.png").write_bytes(png_data)
    print("Generated the DAG based on subtasks!")
    return dag

# async def generate_dag_with_image(plan: PlannerOutput, task_agent_map: dict):
#     dag = build_graph(plan, task_agent_map)
#     png_data = dag.get_graph().draw_mermaid_png()
#     image_path = f"./workflow_graph_images/dag_{str(uuid.uuid4())}.png"
#     Path(image_path).write_bytes(png_data)
#     print("Generated the DAG based on subtasks!")
#     return dag, image_path

async def generate_dag_with_image(
    plan: PlannerOutput,
    task_agent_map: dict[str, str],
    workflow_id: uuid.UUID,
):
    dag = build_graph(
        plan,
        task_agent_map,
        workflow_id,
    )

    image_path = Path(
        f"./workflow_graph_images/dag_{workflow_id}.png"
    )
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(
        dag.get_graph().draw_mermaid_png()
    )

    print("Generated the DAG based on subtasks!")
    return dag, image_path

async def create_plan(
    user_query: str,
    attempts: int = 3,
) -> PlannerOutput:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    planning_query = user_query
    plan = await generate_plan(planning_query)

    for attempt in range(1, attempts + 1):
        print(f"\nGenerated plan ({attempt}/{attempts}):")
        print(plan.model_dump_json(indent=2))

        decision = input(
                    "\nApprove this plan? [y]es, [n]o, [q]uit: "
                ).strip().lower()

        if decision in {"y", "yes"}:
            return plan

        if decision in {"q", "quit"}:
            raise RuntimeError("User cancelled plan approval.")

        if decision not in {"n", "no"}:
            print("Please enter y, n, or q.")
            continue

        if attempt == attempts:
            break

        feedback = input("What should be changed? ").strip()

        if not feedback:
            print("Feedback cannot be empty.")
            continue

        planning_query = f"""
        Original user request:
        {user_query}

        Previous execution plan:
        {plan.model_dump_json(indent=2)}

        Human feedback:
        {feedback}

        Generate a revised execution plan that addresses the feedback.
        """
        plan = await generate_plan(planning_query)

    raise RuntimeError("Maximum plan approval attempts exceeded.")

async def main():
    user_query = input("Enter the query: ")

    await create_dag_pipeline(
        query=user_query,
        status_id=1,
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    from fastapi import FastAPI
    from workflow_apis import router as workflow_router
    app = FastAPI(title="Workflow API")
    app.include_router(workflow_router)
    
