import uuid
import logging
from datetime import datetime
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from workflow_operations import Workflow

# 1. Base Configuration setup
logging.basicConfig(
    level=logging.INFO,                           # Set minimum severity level to log
    format='%(asctime)s - %(levelname)s - %(message)s', # Define log layout structure
    datefmt='%Y-%m-%d %H:%M:%S'                    # Style the timestamp output
)

# 2. Instantiate a module-level logger 
logger = logging.getLogger(__name__)

class WorkflowService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def create_workflow(
        self,
        *,
        name: str,
        description: str,
        graph_image_url: str,
        status_id: int,
        created_by: str = "ADMIN",
    ) -> Workflow:
        with self.session_factory.begin() as session:
            try:
                workflow = Workflow(
                    id=uuid.uuid4(),
                    name=name,
                    description=description,
                    graph_image_url=graph_image_url,
                    status_id=status_id,
                    created_by=created_by,
                )
                session.add(workflow)
                session.flush()
                return workflow
            except SQLAlchemyError:
                logger.exception("Failed to create workflow")
                raise

    def save_workflow(self, workflow: Workflow) -> Workflow:
        with self.session_factory.begin() as session:
            try:
                session.add(workflow)
                session.flush()
                return workflow
            except SQLAlchemyError:
                logger.exception("Failed to save workflow")
                raise
    
    def update_workflow(
        self,
        workflow_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        graph_image_url: str | None = None,
        status_id: int | None = None,
    ) -> Workflow | None:
        with self.session_factory.begin() as session:
            try:
                workflow = session.scalar(
                    select(Workflow).where(
                        Workflow.id == workflow_id,
                        Workflow.deleted_at.is_(None),
                    )
                )

                if workflow is None:
                    return None

                if name is not None:
                    workflow.name = name
                if description is not None:
                    workflow.description = description
                if graph_image_url is not None:
                    workflow.graph_image_url = graph_image_url
                if status_id is not None:
                    workflow.status_id = status_id

                session.flush()
                return workflow
            except SQLAlchemyError:
                logger.exception("Failed to update workflow")
                raise

    def get_workflow(self, workflow_id: uuid.UUID) -> Workflow | None:
        try:
            with self.session_factory() as session:
                return session.scalar(
                    select(Workflow).where(
                        Workflow.id == workflow_id,
                        Workflow.deleted_at.is_(None),
                    )
                )
        except SQLAlchemyError:
            logger.exception("Failed to get workflow")
            raise

    def list_workflows(self) -> Sequence[Workflow]:
        try:
            with self.session_factory() as session:
                statement = (
                    select(Workflow)
                    .where(Workflow.deleted_at.is_(None))
                    .order_by(Workflow.created_date)
                )
                return session.scalars(statement).all()
        except SQLAlchemyError:
            logger.exception("Failed to fetch workflow")
            raise

    def delete_workflow(self, workflow_id: uuid.UUID) -> bool:
        with self.session_factory.begin() as session:
            try:
                workflow = session.scalar(
                    select(Workflow).where(
                        Workflow.id == workflow_id,
                        Workflow.deleted_at.is_(None),
                    )
                )

                if workflow is None:
                    return False

                workflow.deleted_at = datetime.now()
                session.flush()
                return True
            except SQLAlchemyError:
                logger.exception("Failed to delete workflow")
                raise

    def restore_workflow(self, workflow_id: uuid.UUID) -> bool:
        with self.session_factory.begin() as session:
            try:
                workflow = session.scalar(
                    select(Workflow).where(
                        Workflow.id == workflow_id,
                        Workflow.deleted_at.is_not(None),
                    )
                )

                if workflow is None:
                    return False

                workflow.deleted_at = None
                session.flush()
                return True
            except SQLAlchemyError:
                logger.exception("Failed to restore workflow")
                raise


# SessionMaker = sessionmaker(
#     bind=engine,
#     class_=Session,
#     expire_on_commit=False,
# )
# workflow_service = WorkflowService(SessionMaker)

# workflow = Workflow(
#     id=uuid.uuid4(),
#     name="Employee Search",
#     description="Find employees by department",
#     graph_image_url="/images/employee-search.png",
#     status_id=1,
# )

# saved_workflow = workflow_service.save_workflow(workflow)

# updated_workflow = workflow_service.update_workflow(
#     workflow.id,
#     name="Updated Employee Search",
# )

# deleted = workflow_service.delete_workflow(workflow.id)

# restored = workflow_service.restore_workflow(workflow.id)