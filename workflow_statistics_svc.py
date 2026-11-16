import uuid
import logging
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from workflow_operations import WorkflowStatistics

# 1. Base Configuration setup
logging.basicConfig(
    level=logging.INFO,                           # Set minimum severity level to log
    format='%(asctime)s - %(levelname)s - %(message)s', # Define log layout structure
    datefmt='%Y-%m-%d %H:%M:%S'                    # Style the timestamp output
)

# 2. Instantiate a module-level logger 
logger = logging.getLogger(__name__)

class WorkflowStatisticsService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def save_statistics(
        self,
        *,
        workflow_id: uuid.UUID,
        workflow_likes: int = 0,
        workflow_dislikes: int = 0,
        workflow_used: int = 0,
        workflow_success_count: int = 0,
        workflow_failure_count: int = 0,
    ) -> WorkflowStatistics:
        with self.session_factory.begin() as session:
            try:
                statistics = WorkflowStatistics(
                    workflow_id=workflow_id,
                    workflow_likes=workflow_likes,
                    workflow_dislikes=workflow_dislikes,
                    workflow_used=workflow_used,
                    workflow_success_count=workflow_success_count,
                    workflow_failure_count=workflow_failure_count,
                )
                session.add(statistics)
                session.flush()
                return statistics
            except SQLAlchemyError:
                logger.exception("Unable to save workflow statistics")
                raise

    def get_statistics(
        self,
        statistics_id: int,
    ) -> WorkflowStatistics | None:
        try:
            with self.session_factory() as session:
                return session.get(WorkflowStatistics, statistics_id)
        except SQLAlchemyError:
            logger.exception("Unable to fetch workflow statistics")
            raise

    def get_statistics_by_workflow(
        self,
        workflow_id: uuid.UUID,
    ) -> WorkflowStatistics | None:
        try:
            with self.session_factory() as session:
                statement = select(WorkflowStatistics).where(
                    WorkflowStatistics.workflow_id == workflow_id
                )
                return session.scalar(statement)
        except SQLAlchemyError:
            logger.exception("Failed to fetch workflow statistics using workflow ID")
            raise

    def list_statistics(self) -> Sequence[WorkflowStatistics]:
        try:
            with self.session_factory() as session:
                statement = select(WorkflowStatistics).order_by(
                    WorkflowStatistics.workflow_id
                )
                return session.scalars(statement).all()
        except SQLAlchemyError:
            logger.exception("Failed to list workflow statistics")
            raise

    def update_statistics(
        self,
        statistics_id: int,
        *,
        workflow_likes: int | None = None,
        workflow_dislikes: int | None = None,
        workflow_used: int | None = None,
        workflow_success_count: int | None = None,
        workflow_failure_count: int | None = None,
    ) -> WorkflowStatistics | None:
        with self.session_factory.begin() as session:
            try:
                statistics = session.get(WorkflowStatistics, statistics_id)

                if statistics is None:
                    return None

                if workflow_likes is not None:
                    statistics.workflow_likes = workflow_likes

                if workflow_dislikes is not None:
                    statistics.workflow_dislikes = workflow_dislikes

                if workflow_used is not None:
                    statistics.workflow_used = workflow_used

                if workflow_success_count is not None:
                    statistics.workflow_success_count = workflow_success_count

                if workflow_failure_count is not None:
                    statistics.workflow_failure_count = workflow_failure_count
                session.flush()
                return statistics
            except SQLAlchemyError:
                logger.exception("Failed to update workflow statistics")
                raise

    def delete_statistics(self, statistics_id: int) -> bool:
        with self.session_factory.begin() as session:
            try:
                statistics = session.get(WorkflowStatistics, statistics_id)

                if statistics is None:
                    return False

                session.delete(statistics)
                session.flush()
                return True
            except SQLAlchemyError:
                logger.exception("Failed to delete workflow statistics")
                raise

    def record_execution(
        self,
        workflow_id: uuid.UUID,
        *,
        succeeded: bool,
    ) -> WorkflowStatistics:
        with self.session_factory.begin() as session:
            try:
                statement = select(WorkflowStatistics).where(
                    WorkflowStatistics.workflow_id == workflow_id
                )
                statistics = session.scalar(statement)

                if statistics is None:
                    statistics = WorkflowStatistics(
                        workflow_id=workflow_id,
                    )
                    session.add(statistics)

                statistics.workflow_used = (statistics.workflow_used or 0) + 1

                if succeeded:
                    statistics.workflow_success_count = (
                        statistics.workflow_success_count or 0
                    ) + 1
                else:
                    statistics.workflow_failure_count = (
                        statistics.workflow_failure_count or 0
                    ) + 1

                session.flush()
                return statistics
            except SQLAlchemyError:
                logger.exception("Failed to record workflow statistics")
                raise

# from sqlalchemy.orm import Session, sessionmaker

# from workflow_operations import engine

# SessionMaker = sessionmaker(
#     bind=engine,
#     class_=Session,
#     expire_on_commit=False,
# )

# statistics_service = WorkflowStatisticsService(SessionMaker)

# from sqlalchemy.orm import Session, sessionmaker

# from workflow_operations import engine

# SessionMaker = sessionmaker(
#     bind=engine,
#     class_=Session,
#     expire_on_commit=False,
# )

# statistics_service = WorkflowStatisticsService(SessionMaker)