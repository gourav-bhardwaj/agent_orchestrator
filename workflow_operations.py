import uuid
from datetime import datetime
from sqlalchemy import create_engine, ForeignKey, String, Text, DateTime, Integer, text
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship, mapped_column

engine = create_engine("sqlite:///orchestrator.db", echo=True)

class Base(DeclarativeBase):
    pass

class WorkflowStatus(Base):
    __tablename__ = "workflow_status"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    def __repr__(self):
        return f"""WorkflowStatus[
        id = {self.id},
        name = {self.name}
        ]"""

class Workflow(Base):
    __tablename__ = "workflow"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    graph_image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_status.id"),
        nullable=False,
    )
    created_date: Mapped[datetime] = mapped_column(
        default=datetime.now,
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(default="ADMIN", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    status: Mapped[WorkflowStatus] = relationship()

    def __repr__(self):
        return f"""Workflow[
        id = {self.id}
        name = {self.name}
        description = {self.description}
        graph_image_url = {self.graph_image_url}
        status = {self.status.name if self.status else None}
        ]"""

class WorkflowStatistics(Base):
    __tablename__ = "workflow_statistics"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow.id", ondelete="CASCADE"),
        unique=True
    )
    workflow_likes: Mapped[int] = mapped_column(nullable=False, default=0)
    workflow_dislikes: Mapped[int] = mapped_column(nullable=False, default=0)
    workflow_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    workflow_success_count: Mapped[int] = mapped_column(nullable=False, default=0)
    workflow_failure_count: Mapped[int] = mapped_column(nullable=False, default=0)
    workflow: Mapped[Workflow] = relationship()

    def total_workflow_succeed_percentage(self) -> float:
        if self.workflow_used == 0:
            return 0.0
        return round(self.workflow_success_count / self.workflow_used * 100, 2)

    def __repr__(self):
        return f"""WorkflowStatistics[
        workflow_id = {self.workflow_id}
        workflow_likes = {self.workflow_likes}
        workflow_dislikes = {self.workflow_dislikes}
        workflow_used = {self.workflow_used}
        workflow_success_count = {self.workflow_success_count}
        workflow_failure_count = {self.workflow_failure_count}
        ]"""

# Sync with database (creates the tables)
Base.metadata.create_all(engine)