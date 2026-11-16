import uuid
import uvicorn
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from workflow_operations import Workflow, WorkflowStatistics, engine
from workflow_service import WorkflowService
from workflow_statistics_svc import WorkflowStatisticsService


router = APIRouter(
    prefix="/workflows",
    tags=["Workflows"],
)


SessionMaker = sessionmaker(
    bind=engine,
    class_=Session,
    expire_on_commit=False,
)


workflow_service = WorkflowService(SessionMaker)
statistics_service = WorkflowStatisticsService(SessionMaker)


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    graph_image_url: str
    status_id: int
    created_date: datetime
    created_by: str


class WorkflowStatisticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: uuid.UUID
    workflow_likes: int
    workflow_dislikes: int
    workflow_used: int
    workflow_success_count: int
    workflow_failure_count: int


@router.get(
    "",
    response_model=list[WorkflowResponse],
    summary="List active workflows",
)
def list_workflows() -> list[WorkflowResponse]:
    workflows = workflow_service.list_workflows()
    return [WorkflowResponse.model_validate(workflow) for workflow in workflows]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get an active workflow",
)
def get_workflow(workflow_id: uuid.UUID) -> WorkflowResponse:
    workflow = workflow_service.get_workflow(workflow_id)

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' was not found",
        )

    return WorkflowResponse.model_validate(workflow)


@router.get(
    "/{workflow_id}/statistics",
    response_model=WorkflowStatisticsResponse,
    summary="Get statistics for a workflow",
)
def get_workflow_statistics(
    workflow_id: uuid.UUID,
) -> WorkflowStatisticsResponse:
    statistics = statistics_service.get_statistics_by_workflow(workflow_id)

    if statistics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Statistics for workflow '{workflow_id}' were not found",
        )

    return WorkflowStatisticsResponse.model_validate(statistics)


@router.get(
    "/statistics",
    response_model=list[WorkflowStatisticsResponse],
    summary="List workflow statistics",
)
def list_workflow_statistics() -> list[WorkflowStatisticsResponse]:
    statistics = statistics_service.list_statistics()
    return [
        WorkflowStatisticsResponse.model_validate(item)
        for item in statistics
    ]


@router.get(
    "/statistics/{statistics_id}",
    response_model=WorkflowStatisticsResponse,
    summary="Get statistics by statistics ID",
)
def get_statistics(
    statistics_id: int,
) -> WorkflowStatisticsResponse:
    statistics = statistics_service.get_statistics(statistics_id)

    if statistics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow statistics '{statistics_id}' were not found",
        )

    return WorkflowStatisticsResponse.model_validate(statistics)

if __name__ == "__main__":
    # Workflow endpoints
    from fastapi import FastAPI
    from workflow_apis import router as workflow_router
    app = FastAPI(title="Workflow API")
    app.include_router(workflow_router)
    uvicorn.run(app=app, host="127.0.0.1", port=8500)