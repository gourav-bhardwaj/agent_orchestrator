# AI Agent Orchestrator

A multi-agent orchestration application that turns a natural-language request into a structured execution plan, discovers suitable remote agents through an agent registry, builds a dependency-aware workflow graph with LangGraph, and executes the approved workflow through the A2A (Agent-to-Agent) protocol.

The project includes a Gradio chat interface for plan and graph review, SQLite-backed workflow metadata and statistics services, and observability integrations for distributed tracing and LLM monitoring.

> **Project status:** This repository is an implementation/prototype. Some components run as separate processes, and the Gradio workflow path and the standalone workflow-persistence/API path are not fully unified. Review the notes below before treating it as a production deployment.

## Contents

- [Architecture](#architecture)
- [Workflow lifecycle](#workflow-lifecycle)
- [Features](#features)
- [Technology stack](#technology-stack)
- [Repository structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Installation](#installation)
- [Run the application](#run-the-application)
- [Supporting services](#supporting-services)
- [Workflow API](#workflow-api)
- [Prometheus metrics](#prometheus-metrics)
- [Example request](#example-request)
- [Important implementation notes](#important-implementation-notes)
- [Troubleshooting](#troubleshooting)

## Architecture

```text
                         USER
                           |
                           v
                    GRADIO CHAT UI
                           |
                           v
                    PLANNER AGENT
                    (OpenAI Agents SDK)
                           |
                           v
                  STRUCTURED TASK PLAN
                           |
                           v
                    HUMAN APPROVAL
                           |
                           v
                    AGENT REGISTRY
                    (HTTP discovery)
                           |
                           v
                 SPECIALIZED REMOTE AGENTS
                      (A2A protocol)
                           |
                           v
                  DYNAMIC LANGGRAPH DAG
                           |
                           v
                  WORKFLOW GRAPH REVIEW
                           |
                           v
                    HUMAN APPROVAL
                           |
                           v
                   LANGGRAPH EXECUTION
                           |
               +-----------+-----------+
               |           |           |
               v           v           v
            AGENT A     AGENT B     AGENT C
               |           |           |
               +-----------+-----------+
                           |
                           v
                    EXECUTION RESULTS

      OBSERVABILITY: OpenTelemetry | Jaeger | Langfuse
      METRICS:       Prometheus
      PERSISTENCE:   SQLite / SQLAlchemy
```

### Main components

| Component | Responsibility |
|---|---|
| Gradio UI | Accepts user requests and presents the plan, graph, approval controls, and execution output. |
| Planner agent | Uses the OpenAI Agents SDK to decompose a request into structured subtasks. |
| Agent registry | Finds a remote agent for a task using the registry HTTP endpoint. |
| A2A client | Resolves the remote agent's Agent Card and communicates with the agent. |
| LangGraph | Builds and runs a graph whose nodes represent subtasks and whose edges represent dependencies. |
| Workflow services | Provide workflow metadata and statistics persistence using SQLAlchemy and SQLite. |
| OpenTelemetry | Creates distributed traces and exports them over OTLP/gRPC. |
| Langfuse | Provides LLM tracing through OpenAI Agents instrumentation. |
| Prometheus | Exposes application-defined LLM counters and latency histograms. |

## Workflow lifecycle

The Gradio application follows this interaction:

1. **Submit a request** — The user describes the work to be performed.
2. **Generate a plan** — The planner produces subtasks with a name, description, status, execution type, and dependencies.
3. **Review the plan** — The user can approve or reject the proposed plan.
4. **Discover agents** — After plan approval, the application queries the agent registry for an agent matching each subtask.
5. **Build the DAG** — LangGraph nodes and dependency edges are created, and a Mermaid PNG is generated.
6. **Review the graph** — The user can approve or reject the generated workflow graph.
7. **Execute** — Execution starts only after the user selects **Execute Workflow**.
8. **Review results** — The final execution state is displayed in the Gradio chat.

Independent graph nodes can be eligible to run in parallel when the dependency structure allows it. A node with dependencies waits for its upstream nodes.

## Features

### Dynamic task planning

- Uses the OpenAI Agents SDK and the `gpt-4.1-mini` model configured in `main.py`.
- Converts a natural-language request into structured subtasks.
- Models task status as `pending`, `completed`, or `failed`.
- Models execution type as `sync` or `async`.
- Represents dependencies through `depends_on`.

### Agent discovery and A2A communication

- Looks up agents through the registry endpoint.
- Uses the returned agent URL to resolve the remote Agent Card.
- Uses the A2A SDK to communicate with remote agents.
- Supports structured agent response data and artifact-aware invocation code.

The registry lookup is currently configured in `agent_registry.py` as:

```text
GET http://localhost:8000/agent?query=<task description>
```

The response is expected to contain the `task` and `agent_url` fields.

### Dynamic LangGraph workflow

- Creates a LangGraph `StateGraph` from the planner output.
- Adds a node for each planned subtask.
- Adds directed edges based on `depends_on`.
- Connects dependency-free tasks as graph entry points.
- Generates a Mermaid PNG representation of the graph.

Generated graph images are written to `workflow_graph_images/` by the Gradio workflow path.

### Human-in-the-loop controls

The Gradio interface includes separate approval stages for the generated plan and the generated graph. The graph is not executed until the user approves it and selects the execution button.

### Workflow metadata and statistics

The SQLAlchemy models define:

- Workflow metadata, including name, description, graph image path, status, creator, and creation date.
- Workflow statistics, including likes, dislikes, usage count, success count, and failure count.
- Workflow services and REST endpoints for listing and retrieving workflow records and statistics.

The database is SQLite, configured as `sqlite:///orchestrator.db`.

### Observability

**OpenTelemetry and Jaeger**

- Creates spans for orchestrator operations.
- Instruments HTTPX requests.
- Provides FastAPI instrumentation support.
- Exports traces using OTLP over gRPC to `http://localhost:4317`.

**Langfuse**

- Uses `OpenAIAgentsInstrumentor` to instrument OpenAI Agents SDK activity.
- Reads Langfuse credentials and host configuration from environment variables.
- Checks Langfuse authentication when the configuration module is imported.

**Prometheus**

The project defines these metrics:

| Metric | Type | Description |
|---|---|---|
| `llm_requests_total` | Counter | Number of LLM requests |
| `llm_cost_usd_total` | Counter | Estimated LLM cost in USD |
| `llm_input_tokens_total` | Counter | Input tokens consumed |
| `llm_output_tokens_total` | Counter | Output tokens generated |
| `llm_errors_total` | Counter | LLM errors |
| `llm_request_duration_seconds` | Histogram | LLM request duration |

Metrics are labelled by `model` and `agent`.

## Technology stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ |
| Agent framework | OpenAI Agents SDK |
| Agent communication | A2A SDK / A2A protocol |
| Workflow orchestration | LangGraph |
| LLM | OpenAI `gpt-4.1-mini` |
| User interface | Gradio |
| API framework | FastAPI |
| HTTP client | HTTPX |
| Data validation | Pydantic |
| Database | SQLite |
| ORM | SQLAlchemy |
| Distributed tracing | OpenTelemetry |
| Trace backend | Jaeger |
| LLM observability | Langfuse |
| Metrics | Prometheus Client |
| Graph rendering | LangGraph Mermaid PNG rendering |
| Image handling | Pillow |

## Repository structure

```text
ai_orchestrator/
├── main.py
├── agent_registry.py
├── gradio_chat.py
├── webhook.py
├── workflow_apis.py
├── workflow_service.py
├── workflow_operations.py
├── workflow_statistics_svc.py
├── observability.py
├── langfuse_config.py
├── metrics.py
├── prometheus_endpoint.py
├── requirements.txt
├── pyproject.toml
├── uv.lock
├── orchestrator.db
└── workflow_graph_images/
```

| File | Purpose |
|---|---|
| `main.py` | Planner agent, task models, DAG construction, agent selection, and workflow execution functions. |
| `agent_registry.py` | Agent registry lookup and A2A client invocation logic. |
| `gradio_chat.py` | Gradio chat UI and plan/graph approval workflow. |
| `webhook.py` | A2A push-notification webhook endpoint. |
| `workflow_apis.py` | REST endpoints for workflow metadata and statistics. |
| `workflow_service.py` | Workflow persistence operations. |
| `workflow_operations.py` | SQLAlchemy engine, models, and table creation. |
| `workflow_statistics_svc.py` | Workflow statistics persistence and retrieval. |
| `observability.py` | OpenTelemetry tracer configuration, HTTPX instrumentation, and span helper. |
| `langfuse_config.py` | Langfuse client and OpenAI Agents instrumentation setup. |
| `metrics.py` | Prometheus counters and histogram definitions. |
| `prometheus_endpoint.py` | FastAPI `/metrics` and `/health` endpoints. |
| `orchestrator.db` | SQLite database file, if supplied with the repository. |
| `workflow_graph_images/` | Generated workflow graph images. |

## Prerequisites

- Python 3.11 or later.
- Docker, for running Jaeger.
- An OpenAI API key.
- A running agent registry service at the configured endpoint.
- One or more remote agents that expose A2A-compatible endpoints and Agent Cards.
- Langfuse credentials if Langfuse tracing is to be enabled.

## Configuration

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key

LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://your-langfuse-host
```

If your remote A2A agents use push notifications, configure the webhook token and URL as required by the agent implementation:

```env
TOKEN=your_webhook_token
WEBHOOK_URL=http://localhost:8003/a2a/webhook
```

`agent_registry.py` currently uses the registry URL `http://localhost:8000/agent` directly in the code. Update that URL in the source if your registry runs elsewhere.

`observability.py` currently exports OTLP traces to:

```text
http://localhost:4317
```

The model is currently set in `main.py`:

```python
model = "gpt-4.1-mini"
```

Do not commit `.env` or real API credentials to source control.

## Installation

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd ai_orchestrator
```

### 2. Create and activate a virtual environment

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The project also includes `pyproject.toml` and `uv.lock` for environments using `uv`.

### 4. Configure environment variables

Create and populate the `.env` file as described in [Configuration](#configuration).

### 5. Start Jaeger before the application

Run Jaeger all-in-one in a separate terminal:

```bash
docker run --rm \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest
```

Keep this container running while using the application.

- **Jaeger UI:** http://localhost:16686
- **OTLP gRPC receiver:** `localhost:4317`

The application configures its OpenTelemetry OTLP exporter to send traces to this endpoint.

## Run the application

Start the registry service and the required remote A2A agents before submitting workflows. Their implementation and startup commands are external to this repository.

### 1. Start the Gradio application

In another terminal, from the project root with the virtual environment activated:

```bash
python gradio_chat.py
```

The script configures OpenTelemetry and launches the Gradio interface. Open the local URL printed by Gradio.

### 2. Use the chat interface

1. Enter a natural-language workflow request.
2. Submit the request and review the generated plan.
3. Approve or reject the plan.
4. If approved, review the generated DAG image.
5. Approve or reject the graph.
6. Select **Execute Workflow** to run the graph.
7. Review the execution result in the chat.

### 3. Run the command-line workflow path (alternative)

`main.py` also contains a command-line entry point:

```bash
python main.py
```

This path prompts for a request and uses terminal input for plan and agent-selection approval. It is separate from the Gradio interaction flow.

## Supporting services

The following components are separate processes. Start only the ones needed for your setup.

### A2A webhook

Run the webhook server:

```bash
python webhook.py
```

It listens on:

```text
http://127.0.0.1:8003/a2a/webhook
```

The endpoint validates the `X-A2A-Notification-Token` header against the `TOKEN` environment variable before accepting a notification.

### Workflow REST API

Run the workflow API:

```bash
python workflow_apis.py
```

It is configured to listen on:

```text
http://127.0.0.1:8500
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8500/docs
```

### Prometheus metrics API

Run the metrics service with Uvicorn:

```bash
uvicorn prometheus_endpoint:app --host 127.0.0.1 --port 9100
```

Endpoints:

- `http://127.0.0.1:9100/metrics`
- `http://127.0.0.1:9100/health`

The metrics endpoint exposes the custom registry defined in `metrics.py`.

## Workflow API

The workflow router is mounted at `/workflows` when `workflow_apis.py` is run.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/workflows` | List active workflows |
| `GET` | `/workflows/{workflow_id}` | Retrieve an active workflow |
| `GET` | `/workflows/{workflow_id}/statistics` | Retrieve statistics for a workflow |
| `GET` | `/workflows/statistics` | List workflow statistics |
| `GET` | `/workflows/statistics/{statistics_id}` | Retrieve statistics by statistics ID |

The API uses UUIDs for workflow identifiers. See `/docs` on the running API service for the generated OpenAPI specification.

## Prometheus metrics

A Prometheus server can scrape the metrics endpoint:

```yaml
scrape_configs:
  - job_name: "ai-agent-orchestrator"
    metrics_path: /metrics
    static_configs:
      - targets: ["127.0.0.1:9100"]
```

If Prometheus runs inside Docker, `127.0.0.1` refers to the Prometheus container itself. Use a reachable host address or a shared Docker network and configure the target accordingly.

The metric values are produced by the application process that updates the metric objects. The metrics API is a separate process in this repository; for a multi-process deployment, configure a suitable shared metrics architecture or expose metrics from the process that performs the LLM work.

## Example request

A request such as:

> Onboard a new employee, retrieve the department information, create the employee record, and notify the HR and IT teams.

could be decomposed into tasks with dependencies similar to the following illustrative plan:

```json
{
  "subtasks": [
    {
      "name": "get_department",
      "description": "Retrieve the required department information.",
      "status": "pending",
      "execution_type": "sync",
      "depends_on": []
    },
    {
      "name": "create_employee",
      "description": "Create the employee record using the department information.",
      "status": "pending",
      "execution_type": "sync",
      "depends_on": ["get_department"]
    },
    {
      "name": "notify_hr",
      "description": "Notify the HR team about the new employee.",
      "status": "pending",
      "execution_type": "async",
      "depends_on": ["create_employee"]
    },
    {
      "name": "notify_it",
      "description": "Notify the IT team about the new employee.",
      "status": "pending",
      "execution_type": "async",
      "depends_on": ["create_employee"]
    }
  ]
}
```

The corresponding dependency structure is:

```text
              START
                |
                v
          GET_DEPARTMENT
                |
                v
          CREATE_EMPLOYEE
                |
           +----+----+
           |         |
           v         v
        NOTIFY_HR  NOTIFY_IT
           |         |
           +----+----+
                |
                v
               END
```

This is an example of the kind of dependency graph the planner may produce; the actual tasks and dependencies depend on the user's request and the planner output.

## Important implementation notes

Please read these notes before deploying or extending the project:

1. **Registry URL is hard-coded.** The lookup in `agent_registry.py` calls `http://localhost:8000/agent`. Change it in the source if your registry uses another address.
2. **Agent selection differs by entry point.** The command-line path in `main.py` asks for terminal confirmation for each discovered agent. The Gradio path discovers agents after plan approval and does not use that terminal prompt.
3. **The Gradio workflow path does not currently use the complete persistence lifecycle.** The workflow API and SQLAlchemy persistence services exist, but the Gradio execution handler builds and executes the graph directly. Do not assume every Gradio execution is saved through `WorkflowService`.
4. **The standalone workflow API is a separate process.** Running the Gradio app does not automatically start the workflow API.
5. **The Prometheus endpoint is a separate process.** The standalone metrics API has its own in-memory registry. A separate process does not automatically share the counters updated in the Gradio/orchestrator process.
6. **Jaeger is an external dependency for trace viewing.** Start the Jaeger container before launching the Gradio app if you want to receive and inspect traces.
7. **Database status data may need initialization.** The schema is created by `workflow_operations.py`, but the repository code does not automatically populate workflow status reference rows. Ensure the required status records exist before using paths that create workflows with a `status_id`.
8. **DAG validation is limited.** The graph builder checks that referenced dependency names exist. Add cycle detection and validation for duplicate task names and other invalid graph structures before relying on arbitrary planner output.
9. **External services are not included.** The agent registry and specialized A2A agent implementations must be started and configured separately.

## Troubleshooting

### Agent registry connection errors

- Confirm the registry service is running.
- Confirm it is reachable at `http://localhost:8000/agent`.
- Confirm its response contains `task` and `agent_url`.
- Check that the returned agent URL is reachable from the orchestrator process.

### A2A agent invocation errors

- Confirm the remote agent exposes a valid Agent Card.
- Confirm its A2A endpoint is reachable.
- Check the agent's server logs and the orchestrator logs.
- If push notifications are used, verify `WEBHOOK_URL`, `TOKEN`, and the notification-token header agree.

### OpenAI authentication errors

- Confirm `OPENAI_API_KEY` is present in `.env`.
- Confirm the key is valid and available to the process running the application.

### Jaeger does not show traces

- Confirm the Jaeger container is running.
- Confirm port `4317` is published and reachable from the application.
- Confirm the exporter endpoint in `observability.py` matches the Jaeger OTLP gRPC receiver.
- Open http://localhost:16686 and select the `orchestrator-mock` service when traces have arrived.

### Langfuse authentication errors

- Verify `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`.
- Confirm the configured host is reachable.
- Langfuse is optional for running the core orchestration flow, but the current configuration module attempts to initialize and authenticate the client when imported.

### Workflow API or database errors

- Confirm the process is running from the project root so the relative SQLite path resolves as expected.
- Confirm the database file and directory are writable.
- Ensure the required workflow status records exist for operations that reference a status ID.

---

## Contributing

Contributions and improvements are welcome. Before submitting changes, test the affected workflow path and update this README when configuration, service endpoints, or startup commands change.

## License

No license file was included in the supplied project archive. Add a `LICENSE` file and update this section before distributing the repository.
