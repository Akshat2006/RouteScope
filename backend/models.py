"""
RouteScope — SQLAlchemy ORM Models
"""
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    topology_snapshot: Mapped[dict] = mapped_column(JSON, nullable=True)  # nodes + edges
    source_node: Mapped[str] = mapped_column(String(64), nullable=True)
    destination_node: Mapped[str] = mapped_column(String(64), nullable=True)
    survivability_score: Mapped[float] = mapped_column(Float, default=0.0)

    results: Mapped[list["AlgorithmResult"]] = relationship(
        "AlgorithmResult", back_populates="experiment", cascade="all, delete-orphan"
    )
    failure_events: Mapped[list["FailureEvent"]] = relationship(
        "FailureEvent", back_populates="experiment", cascade="all, delete-orphan"
    )


class AlgorithmResult(Base):
    __tablename__ = "algorithm_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id"), nullable=False
    )
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#ffffff")
    path: Mapped[list] = mapped_column(JSON, default=list)
    all_paths: Mapped[list] = mapped_column(JSON, default=list)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    hop_count: Mapped[int] = mapped_column(Integer, default=0)
    runtime_ms: Mapped[float] = mapped_column(Float, default=0.0)
    convergence_ms: Mapped[float] = mapped_column(Float, default=0.0)
    reachable: Mapped[bool] = mapped_column(default=True)
    survivability_score: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="results")


class FailureEvent(Base):
    __tablename__ = "failure_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    affected_elements: Mapped[list] = mapped_column(JSON, default=list)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    description: Mapped[str] = mapped_column(Text, default="")

    experiment: Mapped["Experiment"] = relationship(
        "Experiment", back_populates="failure_events"
    )
