import gradio as gr
from PIL import Image, ImageDraw
import tempfile
import os
import textwrap
import uuid
import main


# --------------------------------------------------
# Mock backend: replace these with your real agents
# and LangGraph orchestrator
# --------------------------------------------------

# def generate_plan(query):
#     """Replace with your planning LLM call."""
#     return [
#         {
#             "name": "research",
#             "description": f"Analyze the request: {query}",
#             "depends_on": [],
#         },
#         {
#             "name": "process",
#             "description": "Process the research results",
#             "depends_on": ["research"],
#         },
#         {
#             "name": "report",
#             "description": "Prepare the final response",
#             "depends_on": ["process"],
#         },
#     ]


# def create_graph_image(plan):
#     """Draw a simple workflow graph without Graphviz."""
#     width, height = 800, max(300, len(plan) * 150)
#     image = Image.new("RGB", (width, height), "white")
#     draw = ImageDraw.Draw(image)

#     node_width, node_height = 320, 70
#     x = (width - node_width) // 2

#     positions = {}

#     for i, task in enumerate(plan):
#         y = 35 + i * 130
#         positions[task["name"]] = (x + node_width // 2, y + node_height // 2)

#         draw.rounded_rectangle(
#             (x, y, x + node_width, y + node_height),
#             radius=12,
#             fill="#E8F0FE",
#             outline="#356AC3",
#             width=2,
#         )

#         draw.text(
#             (x + 18, y + 15),
#             textwrap.shorten(task["name"], width=35),
#             fill="#172B4D",
#         )
#         draw.text(
#             (x + 18, y + 40),
#             "Workflow task",
#             fill="#44546A",
#         )

#         if i > 0:
#             previous = plan[i - 1]["name"]
#             px, py = positions[previous]
#             cx, cy = positions[task["name"]]

#             start = (px, py + node_height // 2)
#             end = (cx, cy - node_height // 2)

#             draw.line((start, end), fill="#356AC3", width=3)
#             draw.polygon(
#                 [
#                     (end[0], end[1]),
#                     (end[0] - 7, end[1] - 12),
#                     (end[0] + 7, end[1] - 12),
#                 ],
#                 fill="#356AC3",
#             )

#     path = os.path.join(tempfile.gettempdir(), "workflow_graph.png")
#     image.save(path)
#     return path


# def execute_workflow(plan):
    # """Replace with your LangGraph invoke/ainvoke call."""
    # completed = [task["name"] for task in plan]
    # return (
    #     "Workflow executed successfully!\n\n"
    #     "Completed tasks:\n"
    #     + "\n".join(f"- {name}" for name in completed)
    # )

async def execute_workflow(query, plan, dag, workflow_id):
    return await dag.ainvoke({
        "user_query": query,
        "workflow_id": workflow_id,
        "tasks": {
            task["name"]: main.Subtask(**task)
            for task in plan
        },
        "results": {},
    })


# --------------------------------------------------
# Chat handlers
# --------------------------------------------------
def plan_to_dicts(plan_output):
    return [
        task.model_dump()
        for task in plan_output.subtasks
    ]

async def send_message(message, history, state):
    if not message.strip():
        return history, state, "", *visibility(state["stage"])

    history = history + [
        {"role": "user", "content": message}
    ]

    stage = state["stage"]

    if stage == "idle":
        plan_output = await main.generate_plan(message)
        plan = [task.model_dump() for task in plan_output.subtasks]
        state = {
            "stage": "plan_pending",
            "query": message,
            "plan": plan,
            "workflow_id": None
        }

        plan_text = "\n".join(
            f"{i + 1}. {task['name']}: {task['description']}"
            for i, task in enumerate(plan)
        )

        history.append({
            "role": "assistant",
            "content": (
                "Here is the proposed plan:\n\n"
                f"{plan_text}\n\n"
                "Please approve the plan, reject it, or send "
                "revision feedback in the message box."
            ),
        })

    # elif stage == "plan_pending":
    #     # A new user message during approval is treated as
    #     # feedback for regenerating the plan.
    #     plan = await main.generate_plan(
    #         state["query"] + "\nUser feedback: " + message
    #     )
    #     state["plan"] = plan

    #     history.append({
    #         "role": "assistant",
    #         "content": (
    #             "I've revised the proposed plan based on your "
    #             "feedback. Please review it and approve or reject."
    #         ),
    #     })

    #     history.append({
    #         "role": "assistant",
    #         "content": "\n".join(
    #             f"{i + 1}. {task['name']}: {task['description']}"
    #             for i, task in enumerate(plan)
    #         ),
    #     })
    elif stage == "plan_pending":
        revised_plan_output = await main.generate_plan(
        f"""
        Original request:
        {state["query"]}

        Current plan:
        {state["plan"]}

        User feedback:
        {message}

        Revise the plan to address the feedback.
        """
        )

        revised_plan = plan_to_dicts(revised_plan_output)
        state["plan"] = revised_plan

        plan_text = "\n".join(
            f"{index + 1}. {task['name']}: {task['description']}"
            for index, task in enumerate(revised_plan)
        )

        history.append({
            "role": "assistant",
            "content": (
                "I revised the plan based on your feedback. "
                "Please review it and approve or provide more feedback.\n\n"
                f"{plan_text}"
            ),
        })

    # elif stage == "graph_pending":
    #     history.append({
    #         "role": "assistant",
    #         "content": (
    #             "Your feedback has been received. Please reject "
    #             "the graph and return to planning if you want to "
    #             "redesign the workflow."
    #         ),
    #     })
    elif stage == "graph_pending":
        revised_plan_output = await main.generate_plan(
        f"""
        Original request:
        {state["query"]}

        Current approved plan:
        {state["plan"]}

        Current workflow graph feedback:
        {message}

        Revise the workflow structure to address the feedback.
        Update task dependencies if necessary.
        Return the revised execution plan.
        """
        )

        revised_plan = plan_to_dicts(revised_plan_output)
        revised_plan_model = main.PlannerOutput(
            subtasks=[
                main.Subtask(**task)
                for task in revised_plan
            ]
        )

        agent_map = {}

        for task in revised_plan_model.subtasks:
            agent = await main.find(task.description)
            agent_map[task.name] = agent.agent_url

        workflow_id = uuid.uuid4()
        dag, graph_path = await main.generate_dag_with_image(
            revised_plan_model,
            agent_map,
            workflow_id
        )

        state["plan"] = revised_plan
        state["graph_path"] = graph_path
        state["runnable_graph"] = dag
        state["stage"] = "graph_pending"
        state["workflow_id"] = workflow_id

        history.append({
            "role": "assistant",
            "content": "I revised the workflow graph based on your feedback.",
        })

        history.append({
            "role": "assistant",
            "content": gr.Image(
                value=graph_path,
                label="Revised workflow graph",
                show_label=True,
            ),
        })

        history.append({
            "role": "assistant",
            "content": (
                "Please review the revised graph and approve it, "
                "or send additional feedback."
            ),
        })

    elif stage == "execution_ready":
        history.append({
            "role": "assistant",
            "content": "The workflow is approved and ready to execute. "
                       "Use the Execute button below.",
        })

    return history, state, "", *visibility(state["stage"])


async def approve_plan(history, state):
    if state["stage"] != "plan_pending":
        return history, state, *visibility(state["stage"])

    plan = main.PlannerOutput(
        subtasks=[main.Subtask(**task) for task in state["plan"]]
    )

    agent_map = {}
    for task in plan.subtasks:
        agent = await main.find(task.description)
        agent_map[task.name] = agent.agent_url

    # graph_path = create_graph_image(state["plan"])
    workflow_id = uuid.uuid4()
    dag, graph_path = await main.generate_dag_with_image(plan, agent_map, workflow_id)
    state["graph_path"] = graph_path
    state["stage"] = "graph_pending"
    state["runnable_graph"] = dag
    state["workflow_id"] = workflow_id

    history = history + [
        {
            "role": "assistant",
            "content": "Plan approved. Review the workflow graph below.",
        },
        {
            "role": "assistant",
            "content": gr.Image(
                value=graph_path,
                label="Generated workflow graph",
                show_label=True,
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Do you approve this workflow graph? "
                "Execution will not start until you approve it."
            ),
        },
    ]

    return history, state, *visibility(state["stage"])


def reject_plan(history, state):
    state = {"stage": "idle", "query": "", "plan": [], "workflow_id": None}
    history.append({
        "role": "assistant",
        "content": "Plan rejected. Send a new request to start again.",
    })
    return history, state, *visibility(state["stage"])


def approve_graph(history, state):
    if state["stage"] != "graph_pending":
        return history, state, *visibility(state["stage"])

    state["stage"] = "execution_ready"
    history.append({
        "role": "assistant",
        "content": (
            "Workflow graph approved. No tasks have run yet. "
            "Click Execute to begin."
        ),
    })
    return history, state, *visibility(state["stage"])


def reject_graph(history, state):
    state = {"stage": "idle", "query": "", "plan": [], "workflow_id": None}
    history.append({
        "role": "assistant",
        "content": (
            "Workflow graph rejected. Send your request again "
            "to create a new plan."
        ),
    })
    return history, state, *visibility(state["stage"])

def format_workflow_result(result):
    import json
    return json.dumps(
        result,
        indent=2,
        default=lambda value: (
            value.model_dump()
            if hasattr(value, "model_dump")
            else str(value)
        ),
    )

async def run_workflow(history, state):
    if state["stage"] != "execution_ready":
        return history, state, *visibility(state["stage"])
    
    result = await execute_workflow(
        state["query"],
        state["plan"],
        state["runnable_graph"],
        state["workflow_id"]
    )
    
    history.append({
        "role": "assistant",
        "content": (
            "Workflow completed:\n\n"
            f"```json\n{format_workflow_result(result)}\n```"
        ),
    })

    state["stage"] = "idle"
    return history, state, *visibility(state["stage"])


# def visibility(stage):
#     return (
#         gr.update(visible=(stage == "plan_pending")),
#         gr.update(visible=(stage == "graph_pending")),
#         gr.update(visible=(stage == "execution_ready")),
#     )
def visibility(stage):
    return (
        gr.update(visible=(stage == "plan_pending")),  # approve plan
        gr.update(visible=(stage == "plan_pending")),  # reject plan
        gr.update(visible=(stage == "graph_pending")), # approve graph
        gr.update(visible=(stage == "graph_pending")), # reject graph
        gr.update(visible=(stage == "execution_ready")), # execute
    )

# --------------------------------------------------
# Custom Gradio interface
# --------------------------------------------------

with gr.Blocks(title="Agent Orchestrator") as demo:
    gr.Markdown("# Agent Orchestrator")
    gr.Markdown(
        "Create a plan, review its graph, and approve execution "
        "without leaving the chat."
    )

    state = gr.State({
        "stage": "idle",
        "query": "",
        "plan": [],
        "workflow_id": None
    })

    chatbot = gr.Chatbot(
        label="Workflow conversation",
        height=520,
        layout="bubble",
    )

    with gr.Row():
        message = gr.Textbox(
            placeholder="Describe the workflow you want to run...",
            label="Message",
            scale=8,
            lines=2,
        )
        send = gr.Button("Send", variant="primary", scale=1)

    with gr.Row():
        approve_plan_btn = gr.Button(
            "Approve Plan",
            variant="primary",
            visible=False,
        )
        reject_plan_btn = gr.Button(
            "Reject Plan",
            variant="stop",
            visible=False,
        )

    with gr.Row():
        approve_graph_btn = gr.Button(
            "Approve Graph",
            variant="primary",
            visible=False,
        )
        reject_graph_btn = gr.Button(
            "Reject Graph",
            variant="stop",
            visible=False,
        )

    execute_btn = gr.Button(
        "Execute Workflow",
        variant="primary",
        visible=False,
    )

    button_outputs = [
        approve_plan_btn,
        reject_plan_btn,
        approve_graph_btn,
        reject_graph_btn,
        execute_btn,
    ]

    send_outputs = [
        chatbot,
        state,
        message,
        *button_outputs
    ]

    send.click(
        send_message,
        inputs=[message, chatbot, state],
        outputs=send_outputs,
    )

    message.submit(
        send_message,
        inputs=[message, chatbot, state],
        outputs=send_outputs,
    )

    approve_plan_btn.click(
        approve_plan,
        inputs=[chatbot, state],
        outputs=[chatbot, state, *button_outputs],
    )

    reject_plan_btn.click(
        reject_plan,
        inputs=[chatbot, state],
        outputs=[chatbot, state, *button_outputs],
    )

    approve_graph_btn.click(
        approve_graph,
        inputs=[chatbot, state],
        outputs=[chatbot, state, *button_outputs],
    )

    reject_graph_btn.click(
        reject_graph,
        inputs=[chatbot, state],
        outputs=[chatbot, state, *button_outputs],
    )

    execute_btn.click(
        run_workflow,
        inputs=[chatbot, state],
        outputs=[chatbot, state, *button_outputs],
    )

    # Initial visibility setup
    # demo.load(
    #     lambda: visibility("idle"),
    #     outputs=[approve_plan_btn, approve_graph_btn, execute_btn, reject_plan_btn, reject_graph_btn],
    # )
    demo.load(
        lambda: visibility("idle"),
        outputs=[*button_outputs],
    )

if __name__ == "__main__":
    from observability import configure_observability
    configure_observability()
    demo.launch(theme=gr.themes.Soft())