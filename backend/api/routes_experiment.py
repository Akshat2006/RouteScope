"""
RouteScope — Experiment History API Routes

POST /api/experiments                → save current results as an experiment
GET  /api/experiments                → list all experiments
GET  /api/experiments/{id}           → get experiment detail
DELETE /api/experiments/{id}         → delete experiment
POST /api/experiments/compare        → compare two experiments
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Experiment, AlgorithmResult as AlgoResultModel, FailureEvent
from ..ingestion.graph_builder import graph_builder

router = APIRouter(tags=["experiments"])


class SaveExperimentRequest(BaseModel):
    name: str
    description: str = ""
    source: str
    destination: str
    results: list[dict]            # AlgorithmResult.to_dict() list
    survivability_score: float = 0.0
    failure_events: list[dict] = []


class CompareRequest(BaseModel):
    experiment_id_a: int
    experiment_id_b: int


@router.post("/experiments")
async def save_experiment(request: SaveExperimentRequest, db: AsyncSession = Depends(get_db)):
    """Save a set of algorithm results as a named experiment."""
    topology_snapshot = graph_builder.to_dict()

    exp = Experiment(
        name=request.name,
        description=request.description,
        source_node=request.source,
        destination_node=request.destination,
        survivability_score=request.survivability_score,
        topology_snapshot=topology_snapshot,
        created_at=datetime.utcnow(),
    )
    db.add(exp)
    await db.flush()  # get exp.id

    for r in request.results:
        db.add(AlgoResultModel(
            experiment_id=exp.id,
            algorithm=r.get("algorithm", ""),
            color=r.get("color", "#ffffff"),
            path=r.get("path", []),
            all_paths=r.get("all_paths", []),
            cost=r.get("cost", 0),
            hop_count=r.get("hop_count", 0),
            runtime_ms=r.get("runtime_ms", 0),
            convergence_ms=r.get("convergence_ms", 0),
            reachable=r.get("reachable", False),
            metadata_=r.get("metadata", {}),
        ))

    for fe in request.failure_events:
        db.add(FailureEvent(
            experiment_id=exp.id,
            event_type=fe.get("type", "unknown"),
            affected_elements=fe.get("affected", []),
            description=fe.get("description", ""),
        ))

    await db.commit()
    return {"success": True, "experiment_id": exp.id, "name": exp.name}


@router.get("/experiments")
async def list_experiments(db: AsyncSession = Depends(get_db)):
    """List all saved experiments (without full result detail)."""
    stmt = select(Experiment).order_by(Experiment.created_at.desc())
    result = await db.execute(stmt)
    experiments = result.scalars().all()
    return {
        "experiments": [
            {
                "id": e.id,
                "name": e.name,
                "description": e.description,
                "created_at": e.created_at.isoformat(),
                "source": e.source_node,
                "destination": e.destination_node,
                "survivability_score": e.survivability_score,
            }
            for e in experiments
        ],
        "count": len(experiments),
    }


@router.get("/experiments/{exp_id}")
async def get_experiment(exp_id: int, db: AsyncSession = Depends(get_db)):
    """Get full experiment detail including all algorithm results."""
    exp = await db.get(Experiment, exp_id)
    if not exp:
        raise HTTPException(404, f"Experiment {exp_id} not found")

    stmt = select(AlgoResultModel).where(AlgoResultModel.experiment_id == exp_id)
    result = await db.execute(stmt)
    algo_results = result.scalars().all()

    stmt2 = select(FailureEvent).where(FailureEvent.experiment_id == exp_id)
    result2 = await db.execute(stmt2)
    failure_events = result2.scalars().all()

    return {
        "id": exp.id,
        "name": exp.name,
        "description": exp.description,
        "created_at": exp.created_at.isoformat(),
        "source": exp.source_node,
        "destination": exp.destination_node,
        "survivability_score": exp.survivability_score,
        "topology_snapshot": exp.topology_snapshot,
        "results": [
            {
                "algorithm": r.algorithm,
                "color": r.color,
                "path": r.path,
                "all_paths": r.all_paths,
                "cost": r.cost,
                "hop_count": r.hop_count,
                "runtime_ms": r.runtime_ms,
                "convergence_ms": r.convergence_ms,
                "reachable": r.reachable,
                "metadata": r.metadata_,
            }
            for r in algo_results
        ],
        "failure_events": [
            {
                "type": fe.event_type,
                "affected": fe.affected_elements,
                "description": fe.description,
                "timestamp": fe.timestamp.isoformat(),
            }
            for fe in failure_events
        ],
    }


@router.delete("/experiments/{exp_id}")
async def delete_experiment(exp_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an experiment and all associated results."""
    exp = await db.get(Experiment, exp_id)
    if not exp:
        raise HTTPException(404, f"Experiment {exp_id} not found")
    await db.delete(exp)
    await db.commit()
    return {"success": True, "deleted_id": exp_id}


@router.post("/experiments/compare")
async def compare_experiments(request: CompareRequest, db: AsyncSession = Depends(get_db)):
    """Side-by-side comparison of two experiments."""
    exp_a = await db.get(Experiment, request.experiment_id_a)
    exp_b = await db.get(Experiment, request.experiment_id_b)

    if not exp_a:
        raise HTTPException(404, f"Experiment {request.experiment_id_a} not found")
    if not exp_b:
        raise HTTPException(404, f"Experiment {request.experiment_id_b} not found")

    async def _get_results(exp_id):
        stmt = select(AlgoResultModel).where(AlgoResultModel.experiment_id == exp_id)
        r = await db.execute(stmt)
        return {row.algorithm: row for row in r.scalars().all()}

    results_a = await _get_results(exp_a.id)
    results_b = await _get_results(exp_b.id)

    comparison = []
    all_algos = sorted(set(list(results_a.keys()) + list(results_b.keys())))
    for algo in all_algos:
        ra = results_a.get(algo)
        rb = results_b.get(algo)
        comparison.append({
            "algorithm": algo,
            "a": {"cost": ra.cost, "hops": ra.hop_count, "runtime": ra.runtime_ms, "reachable": ra.reachable} if ra else None,
            "b": {"cost": rb.cost, "hops": rb.hop_count, "runtime": rb.runtime_ms, "reachable": rb.reachable} if rb else None,
        })

    return {
        "experiment_a": {"id": exp_a.id, "name": exp_a.name, "survivability": exp_a.survivability_score},
        "experiment_b": {"id": exp_b.id, "name": exp_b.name, "survivability": exp_b.survivability_score},
        "comparison": comparison,
    }
