"""Stage 5: agent-driven article generation from user-supplied material.

Usage:
    uv run python -m scripts.05_run_agent \\
        --category politics \\
        --facts inputs/politics_example.txt \\
        [--target-words 700] \\
        [--out output/generated/my_run]

Pipeline: planner → writer → editor (LLM-as-judge) → optional 1-round revise.

Artifacts are always persisted to a per-run directory (``output/generated/<timestamp>_<category>/``
by default, overridable with ``--out``). Article markdown also prints to stdout
so ``> article.md`` keeps working. Editor trace goes to stderr.

OpenTelemetry traces land in ``output/traces/<timestamp>_05_run_agent.jsonl``;
the run directory's ``trace.json`` points at the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src import config
from src.agents.editor import EditorReview, review_draft
from src.agents.planner import plan_article
from src.agents.writer import revise_article, write_article
from src.llm.tracing import setup_tracing, traced


def _log_review(label: str, review: EditorReview) -> None:
    print(
        f"[editor] {label}: score={review.score:.1f}, approved={review.approved}",
        file=sys.stderr,
    )
    for g in review.grounding_issues:
        print(f"[editor]   grounding: {g}", file=sys.stderr)
    for s in review.style_issues:
        print(f"[editor]   style: {s}", file=sys.stderr)
    for a in review.attribution_issues:
        print(f"[editor]   attribution: {a}", file=sys.stderr)


def _resolve_run_dir(override: Path | None, category: str) -> Path:
    if override is not None:
        return override
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return config.GENERATED_DIR / f"{stamp}_{category}"


@traced("stage_05_run_agent")
def main() -> None:
    p = argparse.ArgumentParser(
        description="Generate a BBC-style article from raw user material."
    )
    p.add_argument("--category", required=True, help="Category slug (e.g. politics, world, sports).")
    p.add_argument("--facts", required=True, type=Path, help="Path to a plaintext file with topic + raw material.")
    p.add_argument("--target-words", type=int, default=None, help="Override the planner's chosen article length.")
    p.add_argument("--out", type=Path, default=None, help="Override the auto-generated run directory.")
    args = p.parse_args()

    config.ensure_dirs()
    raw_material = args.facts.read_text()

    run_dir = _resolve_run_dir(args.out, args.category)
    run_dir.mkdir(parents=True, exist_ok=True)

    trace_file = setup_tracing("05_run_agent")
    (run_dir / "trace.json").write_text(json.dumps({"trace_file": str(trace_file)}, indent=2))

    outline = plan_article(args.category, raw_material, args.target_words)
    (run_dir / "outline.json").write_text(outline.model_dump_json(indent=2))

    if not outline.sufficient:
        print(f"[plan] rejected: {outline.rejection_reason}", file=sys.stderr)
        print(f"[run] artifacts: {run_dir}", file=sys.stderr)
        print(f"[trace] {trace_file}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[plan] sufficient — target_word_count={outline.target_word_count}, "
        f"facts={len(outline.extracted_facts)}, quotes={len(outline.quote_anchors)}",
        file=sys.stderr,
    )

    draft = write_article(outline)
    print(f"[writer] initial draft: {len(draft.split())} words", file=sys.stderr)

    initial_review = review_draft(draft, outline)
    _log_review("initial", initial_review)
    final_review = initial_review

    if not initial_review.approved:
        print("[editor] revising...", file=sys.stderr)
        draft = revise_article(draft, outline, initial_review)
        print(f"[writer] revised draft: {len(draft.split())} words", file=sys.stderr)
        final_review = review_draft(draft, outline)
        _log_review("final", final_review)
        if not final_review.approved:
            print(
                "[editor] unresolved after 1 revision round — returning draft anyway",
                file=sys.stderr,
            )
    else:
        print("[editor] approved on first pass", file=sys.stderr)

    (run_dir / "article.md").write_text(draft)
    (run_dir / "reviews.json").write_text(
        json.dumps(
            {
                "initial": initial_review.model_dump(),
                "final": final_review.model_dump(),
            },
            indent=2,
        )
    )
    print(draft)
    print(f"[run] artifacts: {run_dir}", file=sys.stderr)
    print(f"[trace] {trace_file}", file=sys.stderr)


if __name__ == "__main__":
    setup_tracing("05_run_agent")
    main()
