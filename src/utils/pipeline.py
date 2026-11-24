"""One-command pipeline: synthetic data -> cleaning -> monitoring -> priority -> RAG chunks.

Run from the project root::

    python -m src.utils.pipeline              # full run
    python -m src.utils.pipeline --skip-rag   # skip guideline re-indexing

Every stage writes its output to ``data/derived`` so the Streamlit app can read the result
even when PostgreSQL is not configured. Nothing here touches PostgreSQL; use
``python -m db.load --init --results`` for that.
"""

from __future__ import annotations

import argparse
import time

import pandas as pd

from src.config.settings import ensure_data_dirs, get_config, project_path
from src.ingestion.synthetic.generate import main as generate_synthetic
from src.monitoring.reported import run_reported_monitoring
from src.monitoring.routine import run_routine_monitoring
from src.preprocessing.derive import build_village_features
from src.preprocessing.clean import clean_all
from src.priority_engine.capacity import capacity_plan
from src.priority_engine.engine import build_explanation, compute_priority
from src.priority_engine.sensitivity import sensitivity_analysis, stability_summary


def run(skip_rag: bool = False) -> dict[str, object]:
    """Execute every stage in order and return the headline outputs."""
    start = time.time()
    ensure_data_dirs()
    cfg = get_config()

    print("[1/6] Generating synthetic dataset…")
    generate_synthetic()

    print("[2/6] Cleaning + deriving village features…")
    tables, log = clean_all()
    features = build_village_features(tables, cfg.reference_date)
    features.to_csv(project_path("data", "derived", "village_features.csv"), index=False)
    print(f"      {len(features)} villages, {len(log.entries)} cleaning log entries")

    print("[3/6] Routine monitoring…")
    routine = run_routine_monitoring(features)
    routine.to_csv(project_path("data", "derived", "monitoring_results.csv"), index=False)
    print(f"      {int(routine['flag'].sum())} village(s) flagged")

    print("[4/6] Reported-issue monitoring…")
    reported = run_reported_monitoring(
        tables["farmer_complaints"], tables["villages"], cfg.reference_date
    )
    reported.to_csv(project_path("data", "derived", "reported_monitoring.csv"), index=False)
    print(f"      {len(reported)} village(s) with recent complaints")

    print("[5/6] Combined priority engine…")
    priority, factors = compute_priority(features, routine, reported)
    priority["explanation"] = priority.apply(build_explanation, axis=1)
    priority.to_csv(project_path("data", "derived", "priority_scores.csv"), index=False)
    factors.to_csv(project_path("data", "derived", "priority_score_factors.csv"), index=False)
    plan = capacity_plan(priority, tables["staff"])
    print(f"      top village: {priority.iloc[0]['village_name']} ({priority.iloc[0]['priority_score']:.1f})")
    print(f"      capacity: {plan['total_capacity_per_week']} visits/week")

    sensitivity = sensitivity_analysis(features, routine, reported)
    sensitivity.to_csv(project_path("data", "derived", "sensitivity.csv"), index=False)
    stability = stability_summary(sensitivity)
    print(f"      sensitivity: max rank shift {stability['max_abs_shift']} (stable={stability['stable']})")

    if not skip_rag:
        print("[6/6] Guideline chunks for the AI assistant…")
        from src.rag_assistant.ingest import extract_documents, save_chunks

        chunks = extract_documents()
        if chunks:
            save_chunks(chunks)
            print(f"      {len(chunks)} chunks indexed")
        else:
            print("      no guideline documents found - assistant will report that it is unavailable")

    elapsed = time.time() - start
    print(f"\nPipeline finished in {elapsed:.1f}s. Reference date {cfg.reference_date}.")
    return {
        "features": features,
        "routine": routine,
        "reported": reported,
        "priority": priority,
        "factors": factors,
        "capacity": plan,
        "sensitivity": sensitivity,
        "stability": stability,
    }


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run the AgriResolve AI pipeline")
    parser.add_argument("--skip-rag", action="store_true", help="do not rebuild guideline chunks")
    args = parser.parse_args()
    run(skip_rag=args.skip_rag)


if __name__ == "__main__":
    main()
