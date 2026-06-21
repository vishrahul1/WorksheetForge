"""
Multi-phase worksheet generation orchestrator.

Flow:
  1. source_audit          (fixed)
  2. worksheet_skeleton    (fixed) → parse DOCUMENT_HEADER + JSON sections
  3..N. generate_section   (dynamic, one per section from JSON, run in parallel batches)
  N+1. assemble_docx       (fixed, no AI call)
  → Pandoc → DOCX → Supabase Storage → Document record
"""
import asyncio
import json
import logging
import tempfile
import time
from datetime import datetime, timedelta, timezone

import redis as redis_sync
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.document import Document, DocumentVersion
from app.models.run import Run, RunPhase
from app.services.extraction import extract_text
from app.services.generation.diagrams import extract_and_render_diagrams
from app.services.generation.phases import (
    assemble_docx as assemble_docx_phase,
    generate_section,
    parse_section_output,
    parse_skeleton,
    source_audit,
    worksheet_skeleton,
)
from app.services.generation.providers import create_provider
from app.services.pandoc import assemble_docx as pandoc_assemble
from app.services.storage import upload_document

logger = logging.getLogger(__name__)


def _publish(redis_client: redis_sync.Redis, run_id: str, event: dict) -> None:
    redis_client.publish(f"run:{run_id}:progress", json.dumps(event))


# ─── Phase runner helpers ─────────────────────────────────────────────────────

async def _run_fixed_phase(
    db: AsyncSession,
    redis_client: redis_sync.Redis,
    run_id: str,
    phase_order: int,
    phase_name: str,
    phase_fn,
    context: dict,
    provider,
    existing_phases: dict,
    total_phases: int,
    accum: dict,
) -> str:
    """
    Run a single fixed phase (source_audit, worksheet_skeleton).
    Skips if already completed. Returns the phase output text.
    """
    existing = existing_phases.get(phase_name)

    # Skip if already done
    if existing and existing.status == "done" and existing.output:
        logger.info("Run %s — %s already done, skipping", run_id, phase_name)
        accum["tokens_in"] += existing.tokens_in or 0
        accum["tokens_out"] += existing.tokens_out or 0
        _publish(redis_client, run_id, {
            "type": "phase_completed",
            "phase": phase_name,
            "phase_order": phase_order,
            "total_phases": total_phases,
            "tokens_in": existing.tokens_in or 0,
            "tokens_out": existing.tokens_out or 0,
            "skipped": True,
        })
        return existing.output

    # Reuse existing record or create new
    if existing:
        phase_record = existing
        phase_record.status = "running"
        phase_record.started_at = datetime.now(timezone.utc)
        phase_record.error_message = None
        phase_record.output = None
    else:
        phase_record = RunPhase(
            run_id=run_id,
            phase_name=phase_name,
            phase_order=phase_order,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(phase_record)

    await db.commit()
    await db.refresh(phase_record)

    _publish(redis_client, run_id, {
        "type": "phase_started",
        "phase": phase_name,
        "phase_order": phase_order,
        "total_phases": total_phases,
    })

    try:
        loop = asyncio.get_event_loop()
        result_data = await loop.run_in_executor(
            None,
            lambda: phase_fn(run_id, phase_name, context, provider),
        )

        phase_record.status = "done"
        phase_record.output = result_data["output"]
        phase_record.prompt_sent = result_data.get("prompt_sent", "")
        phase_record.tokens_in = result_data["tokens_in"]
        phase_record.tokens_out = result_data["tokens_out"]
        phase_record.completed_at = datetime.now(timezone.utc)
        accum["tokens_in"] += result_data["tokens_in"]
        accum["tokens_out"] += result_data["tokens_out"]
        accum["cost"] += result_data["cost_usd"]
        context["phase_outputs"][phase_name] = result_data["output"]
        await db.commit()

        _publish(redis_client, run_id, {
            "type": "phase_completed",
            "phase": phase_name,
            "phase_order": phase_order,
            "total_phases": total_phases,
            "tokens_in": result_data["tokens_in"],
            "tokens_out": result_data["tokens_out"],
        })
        return result_data["output"]

    except Exception as exc:
        logger.exception("Phase %s failed for run %s: %s", phase_name, run_id, exc)
        phase_record.status = "failed"
        phase_record.error_message = str(exc)
        phase_record.completed_at = datetime.now(timezone.utc)
        await db.commit()
        _publish(redis_client, run_id, {
            "type": "phase_failed",
            "phase": phase_name,
            "error": str(exc),
        })
        raise


async def _run_section_batch(
    db: AsyncSession,
    redis_client: redis_sync.Redis,
    run_id: str,
    batch: list[tuple[int, dict]],   # [(phase_order, section_spec), ...]
    context: dict,
    provider,
    existing_phases: dict,
    total_phases: int,
    accum: dict,
) -> bool:
    """
    Run a batch of sections in parallel.
    DB operations are sequential; only the Claude API calls are concurrent.
    Returns True if any section in the batch failed.
    """
    active: list[tuple[int, dict, RunPhase]] = []

    # Step 1 — create/reuse RunPhase records (sequential DB ops)
    for phase_order, section_spec in batch:
        section_id = section_spec["id"]
        existing = existing_phases.get(section_id)

        if existing and existing.status == "done" and existing.output:
            logger.info("Run %s — %s already done, skipping", run_id, section_id)
            context["phase_outputs"][section_id] = existing.output
            accum["tokens_in"] += existing.tokens_in or 0
            accum["tokens_out"] += existing.tokens_out or 0
            _publish(redis_client, run_id, {
                "type": "phase_completed",
                "phase": section_id,
                "phase_label": section_spec.get("title", section_id),
                "phase_order": phase_order,
                "total_phases": total_phases,
                "skipped": True,
            })
            continue

        if existing:
            phase_record = existing
            phase_record.status = "running"
            phase_record.started_at = datetime.now(timezone.utc)
            phase_record.error_message = None
            phase_record.output = None
        else:
            phase_record = RunPhase(
                run_id=run_id,
                phase_name=section_id,
                phase_order=phase_order,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(phase_record)

        await db.commit()
        await db.refresh(phase_record)

        _publish(redis_client, run_id, {
            "type": "phase_started",
            "phase": section_id,
            "phase_label": section_spec.get("title", section_id),
            "phase_order": phase_order,
            "total_phases": total_phases,
        })

        active.append((phase_order, section_spec, phase_record))

    if not active:
        return False

    # Step 2 — run Claude calls in parallel (pure IO, no DB access)
    loop = asyncio.get_event_loop()
    futures = [
        loop.run_in_executor(
            None,
            lambda spec=spec: generate_section(spec, run_id, context, provider),
        )
        for _, spec, _ in active
    ]
    results = await asyncio.gather(*futures, return_exceptions=True)

    # Step 3 — update records sequentially
    any_failed = False
    for (phase_order, section_spec, phase_record), result in zip(active, results):
        section_id = section_spec["id"]

        if isinstance(result, Exception):
            logger.exception("Section %s failed: %s", section_id, result)
            phase_record.status = "failed"
            phase_record.error_message = str(result)
            phase_record.completed_at = datetime.now(timezone.utc)
            any_failed = True

            # Store a placeholder so assemble_docx includes a visible warning
            # instead of silently skipping this section from the document
            placeholder = (
                f"## QUESTIONS\n\n"
                f"> ⚠ **This section failed to generate.**\n"
                f"> Error: {str(result)[:300]}\n"
                f"> Retry the run to regenerate this section.\n\n"
                f"## SOLUTIONS\n\n"
                f"> No solutions available — section generation failed.\n"
            )
            phase_record.output = placeholder
            context["phase_outputs"][section_id] = placeholder

            _publish(redis_client, run_id, {
                "type": "phase_failed",
                "phase": section_id,
                "error": str(result),
            })
        else:
            # Split content (for Word) from metadata (for context only)
            clean_content, section_metadata = parse_section_output(result["output"])

            phase_record.status = "done"
            phase_record.output = clean_content   # Word document gets clean content only
            phase_record.prompt_sent = result.get("prompt_sent", "")
            phase_record.tokens_in = result["tokens_in"]
            phase_record.tokens_out = result["tokens_out"]
            phase_record.completed_at = datetime.now(timezone.utc)
            context["phase_outputs"][section_id] = clean_content
            accum["tokens_in"] += result["tokens_in"]
            accum["tokens_out"] += result["tokens_out"]
            accum["cost"] += result["cost_usd"]

            # Accumulate metadata so subsequent sections are aware of what was covered
            if section_metadata:
                entry = f"[{section_spec.get('title', section_id)}] {section_metadata}"
                context.setdefault("sections_metadata", []).append(entry)
                logger.info(
                    "[%s] Stored metadata for %s (%d chars)",
                    run_id, section_id, len(section_metadata),
                )

            _publish(redis_client, run_id, {
                "type": "phase_completed",
                "phase": section_id,
                "phase_label": section_spec.get("title", section_id),
                "phase_order": phase_order,
                "total_phases": total_phases,
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
            })

        await db.commit()

    return any_failed


# ─── Main pipeline ────────────────────────────────────────────────────────────

async def run_generation_pipeline(run_id: str) -> None:
    """Main orchestration coroutine. Called from the RQ worker task."""
    redis_client = redis_sync.from_url(settings.redis_url, decode_responses=True)

    async with AsyncSessionLocal() as db:
        # Load run + project + files
        from app.models.project import Project
        result = await db.execute(
            select(Run)
            .where(Run.id == run_id)
            .options(
                selectinload(Run.project).selectinload(Project.files)
            )
        )
        run = result.scalar_one_or_none()
        if not run:
            logger.error("Run %s not found", run_id)
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        provider = create_provider(
            provider_override=run.llm_provider,
            model_override=run.llm_model,
        )
        logger.info("Run %s using provider: %s", run_id, provider.provider_name)

        # Load existing phases (retry support — skips completed phases)
        existing_result = await db.execute(
            select(RunPhase)
            .where(RunPhase.run_id == run_id)
            .order_by(RunPhase.phase_order)
        )
        existing_phases: dict[str, RunPhase] = {
            p.phase_name: p for p in existing_result.scalars().all()
        }

        project = run.project
        selected_ids = set(run.selected_file_ids or [])
        files = [f for f in project.files if not selected_ids or f.id in selected_ids]

        source_parts = [f.extracted_text for f in files if f.extracted_text]
        source_text = "\n\n".join(source_parts) or "(No source text available)"

        # Restore phase outputs from already-completed phases
        context: dict = {
            "run_id": run_id,
            "project_id": project.id,
            "system_instructions": project.system_instructions or "",
            "source_text": source_text,
            "phase_outputs": {
                name: rec.output
                for name, rec in existing_phases.items()
                if rec.status == "done" and rec.output
            },
            "document_header": "",
            "sections": [],
        }

        # Restore document_header and sections if skeleton already completed
        if "worksheet_skeleton" in context["phase_outputs"]:
            header, sections = parse_skeleton(context["phase_outputs"]["worksheet_skeleton"])
            context["document_header"] = header
            context["sections"] = sections

        accum = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}

        _publish(redis_client, run_id, {
            "type": "run_started", "run_id": run_id, "status": "running",
        })

        try:
            # ── Phase 1: source_audit ─────────────────────────────────────────
            await _run_fixed_phase(
                db, redis_client, run_id, 0, "source_audit",
                source_audit, context, provider, existing_phases,
                total_phases=2,  # will be updated once skeleton is parsed
                accum=accum,
            )

            # ── Phase 2: worksheet_skeleton ───────────────────────────────────
            skeleton_output = await _run_fixed_phase(
                db, redis_client, run_id, 1, "worksheet_skeleton",
                worksheet_skeleton, context, provider, existing_phases,
                total_phases=2,
                accum=accum,
            )

            # Parse skeleton — extract Word header + section JSON
            if "document_header" not in context or not context.get("sections"):
                header, sections = parse_skeleton(skeleton_output)
                context["document_header"] = header
                context["sections"] = sections

            sections = context["sections"]
            if not sections:
                raise ValueError(
                    "Skeleton produced no sections. Check system_instructions and retry."
                )

            # Pre-assign Q number ranges to every section so parallel sections
            # don't overlap (e.g. Section 1 gets Q1–Q20, Section 2 gets Q21–Q35)
            q_cursor = 1
            for sec in sections:
                count = sec.get("question_count", 10)
                sec["start_question"] = q_cursor
                sec["end_question"] = q_cursor + count - 1
                q_cursor += count
                logger.info(
                    "Section %s assigned Q%d–Q%d",
                    sec["id"], sec["start_question"], sec["end_question"],
                )

            # Initialise metadata accumulator — filled as each section completes
            context.setdefault("sections_metadata", [])

            # total_phases = source_audit + skeleton + sections + assemble
            total_phases = 2 + len(sections) + 1
            parallel = max(1, run.parallel_sections or 1)
            logger.info(
                "Run %s — %d sections, parallel=%d, total_phases=%d",
                run_id, len(sections), parallel, total_phases,
            )

            # ── Phases 3..N: section generation (parallel batches) ────────────
            section_list = [(2 + i, s) for i, s in enumerate(sections)]
            batches = [
                section_list[i: i + parallel]
                for i in range(0, len(section_list), parallel)
            ]

            any_section_failed = False
            for batch_index, batch in enumerate(batches):
                failed = await _run_section_batch(
                    db, redis_client, run_id, batch,
                    context, provider, existing_phases, total_phases, accum,
                )
                if failed:
                    any_section_failed = True

                # Inter-batch delay to respect rate limits
                if settings.phase_delay_seconds > 0 and batch_index < len(batches) - 1:
                    logger.info(
                        "Waiting %ds between batches (PHASE_DELAY_SECONDS)",
                        settings.phase_delay_seconds,
                    )
                    await asyncio.sleep(settings.phase_delay_seconds)

            if any_section_failed:
                # Don't abort — assemble with partial content + placeholders.
                # Failed sections have placeholder output already stored in context.
                # User can retry to regenerate only the failed sections.
                logger.warning(
                    "Run %s: one or more sections failed — continuing assembly with partial content",
                    run_id,
                )
                run.error_message = (
                    "Some sections failed to generate. "
                    "The document has been created with placeholders. "
                    "Retry the run to regenerate failed sections only."
                )
                await db.commit()

            # ── Phase N+1: assemble_docx (no AI call) ─────────────────────────
            assemble_order = 2 + len(sections)
            assemble_existing = existing_phases.get("assemble_docx")

            if assemble_existing and assemble_existing.status == "done" and assemble_existing.output:
                final_markdown = assemble_existing.output
                logger.info("Run %s — assemble_docx already done, skipping", run_id)
            else:
                if assemble_existing:
                    ar = assemble_existing
                    ar.status = "running"
                    ar.started_at = datetime.now(timezone.utc)
                    ar.error_message = None
                    ar.output = None
                else:
                    ar = RunPhase(
                        run_id=run_id,
                        phase_name="assemble_docx",
                        phase_order=assemble_order,
                        status="running",
                        started_at=datetime.now(timezone.utc),
                    )
                    db.add(ar)
                await db.commit()
                await db.refresh(ar)

                _publish(redis_client, run_id, {
                    "type": "phase_started",
                    "phase": "assemble_docx",
                    "phase_order": assemble_order,
                    "total_phases": total_phases,
                })

                assemble_result = assemble_docx_phase(run_id, context, provider)
                final_markdown = assemble_result["output"]

                ar.status = "done"
                ar.output = final_markdown
                ar.completed_at = datetime.now(timezone.utc)
                context["phase_outputs"]["assemble_docx"] = final_markdown
                await db.commit()

                _publish(redis_client, run_id, {
                    "type": "phase_completed",
                    "phase": "assemble_docx",
                    "phase_order": assemble_order,
                    "total_phases": total_phases,
                })

            # ── Convert to DOCX and upload ─────────────────────────────────────
            _publish(redis_client, run_id, {"type": "assembling_docx", "run_id": run_id})

            with tempfile.TemporaryDirectory() as tmpdir:
                updated_markdown, image_paths = extract_and_render_diagrams(
                    final_markdown, tmpdir
                )
                docx_bytes = pandoc_assemble(updated_markdown, image_paths)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=settings.document_ttl_hours)

            document = Document(
                run_id=run_id,
                project_id=project.id,
                title=f"{project.name} — Worksheet",
                current_version=1,
                expires_at=expires_at,
            )
            db.add(document)
            await db.flush()

            # Retry upload up to 3 times — Supabase Storage can have transient failures
            storage_path = None
            for upload_attempt in range(1, 4):
                try:
                    storage_path = upload_document(document.id, 1, docx_bytes)
                    break
                except Exception as upload_exc:
                    if upload_attempt == 3:
                        raise
                    wait_s = 10 * upload_attempt
                    logger.warning(
                        "Upload attempt %d/3 failed, retrying in %ds: %s",
                        upload_attempt, wait_s, upload_exc,
                    )
                    time.sleep(wait_s)
            doc_version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                storage_path=storage_path,
                size_bytes=len(docx_bytes),
            )
            db.add(doc_version)

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.total_tokens_in = accum["tokens_in"]
            run.total_tokens_out = accum["tokens_out"]
            run.estimated_cost_usd = accum["cost"]
            await db.commit()

            _publish(redis_client, run_id, {
                "type": "run_completed",
                "run_id": run_id,
                "document_id": document.id,
                "expires_at": expires_at.isoformat(),
                "tokens_in": accum["tokens_in"],
                "tokens_out": accum["tokens_out"],
                "cost_usd": accum["cost"],
            })
            logger.info(
                "Run %s completed. Document %s expires at %s",
                run_id, document.id, expires_at,
            )

        except Exception as exc:
            logger.exception("Run %s failed: %s", run_id, exc)
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            run.total_tokens_in = accum["tokens_in"]
            run.total_tokens_out = accum["tokens_out"]
            run.estimated_cost_usd = accum["cost"]
            await db.commit()
            _publish(redis_client, run_id, {
                "type": "run_failed",
                "run_id": run_id,
                "error": str(exc),
            })
