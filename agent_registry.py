import os
from pydantic import BaseModel, Field
from typing import Literal
import httpx
import uuid
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
    SendMessageConfiguration,
    TaskPushNotificationConfig,
    Task, 
    TaskStatusUpdateEvent, 
    TaskState
)
from a2a.client import create_client, ClientCallContext
from a2a.client import (
    A2ACardResolver,
    create_client
)
from a2a.client.errors import (
    A2AClientTimeoutError
)
from observability import span
import logging

logger = logging.getLogger("orchestrator")

class StructuredResponse(BaseModel):
    message: str = Field(description="Message to get the information received from the agent tool")
    status: Literal["done", "pending", "failure"] = Field(description="Status of the task as per the given agent tool response")

class TaskAgent(BaseModel):
    task: str
    agent_url: str

# async def find(query: str) -> TaskAgent:
#     async with httpx.AsyncClient() as client:
#         response = await client.get(
#             "http://localhost:8000/agent",
#             params={"query": query},
#             timeout=60
#         )
#         response.raise_for_status()
#         print(response.json())
#         return TaskAgent.model_validate(response.json())

from observability import span

async def find(query: str) -> TaskAgent:
    with span(
        "agent_lookup",
        query_length=len(query),
    ) as current_span:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:8000/agent",
                params={"query": query},
                timeout=60,
            )
            response.raise_for_status()

            agent = TaskAgent.model_validate(response.json())
            current_span.set_attribute("agent.url", agent.agent_url)
            return agent            

# async def invoke(agent: TaskAgent, task: str, query: str) -> StructuredResponse:
#     async with httpx.AsyncClient() as http:
#         resolver = A2ACardResolver(
#             http,
#             agent.agent_url
#         )
#         agent_card = (
#             await resolver.get_agent_card()
#         )
#         client = await create_client(
#             agent_card
#         )

#         message = Message(
#             role=Role.ROLE_USER,
#             message_id=str(uuid.uuid4()),
#             parts=[
#                 Part(
#                     text=(
#                         f"CURRENT TASK: {task}"
#                         f"USER QUERY (EXTRACT DETAILS): {query}"
#                     )
#                 )
#             ]
#         )

#         request = SendMessageRequest(
#             message=message,
#             configuration=SendMessageConfiguration(
#                 task_push_notification_config=TaskPushNotificationConfig(
#                     url=os.getenv("WEBHOOK_URL"),
#                     token=os.getenv("TOKEN")
#                 ),
#                 return_immediately=True
#             )
#         )
#         async with client:
#             async for resp in client.send_message(
#                 request=request
#             ):
#                 print(f"RESPONSE: {resp}")
#     await client.close()


# from collections.abc import AsyncIterator
# async def invoke(tagent: TaskAgent) -> AsyncIterator[StructuredResponse]:
#     try:
#         async with httpx.AsyncClient(
#             trust_env=False,
#             timeout=10.0,
#         ) as http:
#             resolver = A2ACardResolver(http, tagent.agent_url)
#             agent_card = await resolver.get_agent_card()
#             client = await create_client(agent_card)

#             message = Message(
#                 role=Role.ROLE_USER,
#                 message_id=str(uuid.uuid4()),
#                 parts=[
#                     Part(
#                         text=(
#                             f"CURRENT TASK: {tagent.task}"
#                         )
#                     )
#                 ]
#             )

#             request = SendMessageRequest(
#                 message=message
#             )

#             async with client:
#                 async for resp in client.send_message(request=request):
#                     print(f"RESPONSE: {resp}")

#                     if isinstance(resp, Task):
#                         state = resp.status.state
#                     elif isinstance(resp, TaskStatusUpdateEvent):
#                         state = resp.status.state
#                     else:
#                         continue

#                     if state == TaskState.TASK_STATE_COMPLETED:
#                         return StructuredResponse(
#                             message="Task completed successfully.",
#                             status="done",
#                         )
#                     if state in {
#                         TaskState.TASK_STATE_FAILED,
#                         TaskState.TASK_STATE_CANCELED,
#                         TaskState.TASK_STATE_REJECTED,
#                     }:
#                         return StructuredResponse(
#                             message=f"Task ended with state: {state}",
#                             status="failure",
#                         )
#         return StructuredResponse(
#             message="Task is still in progress.",
#             status="pending",
#         )
#     except A2AClientTimeoutError as e:
#         print(f"Error: {e}")
#         return await invoke(tagent)

from collections.abc import AsyncIterator

async def invoke(
    tagent: TaskAgent,
) -> AsyncIterator[StructuredResponse]:
    async with httpx.AsyncClient(
        trust_env=False,
        timeout=10.0,
    ) as http:
        resolver = A2ACardResolver(http, tagent.agent_url)
        agent_card = await resolver.get_agent_card()
        client = await create_client(agent_card)

        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=f"CURRENT TASK: {tagent.task}")],
        )

        request = SendMessageRequest(message=message)

        async with client:
            async for resp in client.send_message(request=request):
                if isinstance(resp, Task):
                    state = resp.status.state
                elif isinstance(resp, TaskStatusUpdateEvent):
                    state = resp.status.state
                else:
                    yield StructuredResponse(
                        message=f"Unknown A2A response: {type(resp).__name__}",
                        status="failure",
                    )
                    return

                if state == TaskState.TASK_STATE_COMPLETED:
                    yield StructuredResponse(
                        message="Task completed successfully.",
                        status="done",
                    )
                    return

                if state in {
                    TaskState.TASK_STATE_FAILED,
                    TaskState.TASK_STATE_CANCELED,
                    TaskState.TASK_STATE_REJECTED,
                }:
                    yield StructuredResponse(
                        message=f"Task ended with state: {state}",
                        status="failure",
                    )
                    return

                yield StructuredResponse(
                    message=f"Task status updated: {state}",
                    status="pending",
                )

from a2a.helpers.proto_helpers import get_stream_response_text
# Artifact-aware alternative; the original invoke() is intentionally preserved.
async def invoke_with_artifacts(
    tagent: TaskAgent,
) -> AsyncIterator[StructuredResponse]:
    async with httpx.AsyncClient(
        trust_env=False,
        timeout=10.0,
    ) as http:
        resolver = A2ACardResolver(http, tagent.agent_url)
        agent_card = await resolver.get_agent_card()
        client = await create_client(agent_card)

        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=f"CURRENT TASK: {tagent.task}")],
        )

        # request = SendMessageRequest(message=message)

        request = SendMessageRequest(
            message=message,
            # configuration=SendMessageConfiguration(
            #     task_push_notification_config=TaskPushNotificationConfig(
            #         url=os.getenv("WEBHOOK_URL"),
            #         token=os.getenv("TOKEN")
            #     ),
            #     return_immediately=True
            # )
        )

        async with client:
            async for response in client.send_message(request=request):
                response_message = get_stream_response_text(response)

                if response.HasField("artifact_update"):
                    yield StructuredResponse(
                        message=response_message or "Artifact received.",
                        status="pending",
                    )
                    continue

                if response.HasField("message"):
                    yield StructuredResponse(
                        message=response_message,
                        status="done",
                    )
                    return

                if response.HasField("task"):
                    state = response.task.status.state
                elif response.HasField("status_update"):
                    state = response.status_update.status.state
                else:
                    yield StructuredResponse(
                        message="A2A response contained no recognized payload.",
                        status="failure",
                    )
                    return

                if state == TaskState.TASK_STATE_COMPLETED:
                    yield StructuredResponse(
                        message=response_message or "Task completed successfully.",
                        status="done",
                    )
                    return

                if state in {
                    TaskState.TASK_STATE_FAILED,
                    TaskState.TASK_STATE_CANCELED,
                    TaskState.TASK_STATE_REJECTED,
                }:
                    yield StructuredResponse(
                        message=response_message or f"Task ended with state: {state}",
                        status="failure",
                    )
                    return

                yield StructuredResponse(
                    message=response_message or f"Task status updated: {state}",
                    status="pending",
                )

# --------------------------------

import asyncio
import random
import httpx
from a2a.client.errors import A2AClientTimeoutError

MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 1

async def invoke_with_artifacts_v1(tagent: TaskAgent) -> AsyncIterator[StructuredResponse]:
    message_id = str(uuid.uuid4())
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=30.0,
                    write=10.0,
                    pool=10.0,
                ),
            ) as http:
                resolver = A2ACardResolver(http, tagent.agent_url)
                agent_card = await resolver.get_agent_card()
                client = await create_client(agent_card)

                message = Message(
                    role=Role.ROLE_USER,
                    message_id=message_id,
                    parts=[Part(text=f"CURRENT TASK: {tagent.task}")],
                )

                request = SendMessageRequest(message=message)

                async with client:
                    async for response in client.send_message(request=request):
                        response_message = get_stream_response_text(response)
                        if response.HasField("artifact_update"):
                            yield StructuredResponse(
                                message=response_message or "Artifact received.",
                                status="pending",
                            )
                            continue
        
                        if response.HasField("message"):
                            yield StructuredResponse(
                                message=response_message,
                                status="done",
                            )
                            return
        
                        if response.HasField("task"):
                            state = response.task.status.state
                        elif response.HasField("status_update"):
                            state = response.status_update.status.state
                        else:
                            yield StructuredResponse(
                                message="A2A response contained no recognized payload.",
                                status="failure",
                            )
                            return
        
                        if state == TaskState.TASK_STATE_COMPLETED:
                            yield StructuredResponse(
                                message=response_message or "Task completed successfully.",
                                status="done",
                            )
                            return
        
                        if state in {
                            TaskState.TASK_STATE_FAILED,
                            TaskState.TASK_STATE_CANCELED,
                            TaskState.TASK_STATE_REJECTED,
                        }:
                            yield StructuredResponse(
                                message=response_message or f"Task ended with state: {state}",
                                status="failure",
                            )
                            return
        
                        yield StructuredResponse(
                            message=response_message or f"Task status updated: {state}",
                            status="pending",
                        )
            return
        except (A2AClientTimeoutError, httpx.TimeoutException) as error:
            if attempt == MAX_ATTEMPTS:
                yield StructuredResponse(
                    message=f"A2A request timed out after {MAX_ATTEMPTS} attempts: {error}",
                    status="failure",
                )
                return

            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            delay += random.uniform(0, 0.25)

            logging.info(
                f"A2A timeout for `{tagent.task}`. "
                f"Retrying {attempt + 1}/{MAX_ATTEMPTS} in {delay:.2f}s"
            )
            await asyncio.sleep(delay)