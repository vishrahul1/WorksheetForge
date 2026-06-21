"""
Worksheet generation phases.

Pipeline (fixed bookends, dynamic middle):
  1. source_audit        — analyse source material (fixed)
  2. worksheet_skeleton  — outputs DOCUMENT_HEADER + JSON_PLAN (fixed)
     └─ orchestrator parses JSON_PLAN → creates one phase per section
  3..N. generate_section — one call per section (dynamic, driven by JSON_PLAN)
  N+1. assemble_docx     — joins everything into final markdown (fixed, no AI call)

Skeleton output format:
  ---DOCUMENT_HEADER---
  [Premium Word cover page markdown]
  ---END_HEADER---

  ---JSON_PLAN---
  {"sections": [{...}, ...]}
  ---END_JSON---

Each section phase outputs:
  ## QUESTIONS
  Q1. ...
  ## SOLUTIONS
  **Q1.** Answer: ... — explanation (no question restatement)
"""
import json
import logging
import re
from typing import Any

from app.services.generation.providers.base import LLMProvider

logger = logging.getLogger(__name__)

MAX_TOKENS = 8192

QUESTIONS_MARKER = "## QUESTIONS"
SOLUTIONS_MARKER = "## SOLUTIONS"

HEADER_START = "---DOCUMENT_HEADER---"
HEADER_END = "---END_HEADER---"
JSON_START = "---JSON_PLAN---"
JSON_END = "---END_JSON---"
META_START = "---SECTION_META---"
META_END = "---END_META---"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _system_prompt(system_instructions: str) -> str:
    return (
        "You are an expert educator creating premium academic worksheets for "
        "competitive examinations (Olympiad, JEE, NEET).\n\n"

        "## ABSOLUTE OUTPUT FORMAT RULES — NEVER VIOLATE THESE\n\n"
        "When generating a worksheet section you MUST output EXACTLY these two "
        "heading lines — no variations, no alternatives, no omissions:\n\n"
        "  ## QUESTIONS\n"
        "  ## SOLUTIONS\n\n"
        "These two lines are machine-parsed markers. "
        "If either marker is missing or changed (e.g. '## Questions', '# QUESTIONS', "
        "'**QUESTIONS**', 'Questions:', 'Section Questions') the entire section will "
        "be lost from the final document.\n\n"
        "VIOLATIONS THAT WILL BREAK THE SYSTEM:\n"
        "- Using any capitalisation other than ALL-CAPS: ## QUESTIONS / ## SOLUTIONS\n"
        "- Adding anything between ## and QUESTIONS or SOLUTIONS\n"
        "- Replacing ## with # or ###\n"
        "- Writing the marker inside a bold, italic, or other formatting\n"
        "- Skipping ## SOLUTIONS because you think it is not needed\n"
        "- Writing solutions inside the ## QUESTIONS block\n\n"

        "## SCOPE CONTROL — MANDATORY\n\n"
        "1. Do NOT add extra questions beyond the exact count specified.\n"
        "2. Do NOT add introductory text, closing remarks, preamble, or meta-commentary. "
        "Output the requested content directly — nothing surrounding it.\n"
        "3. Do NOT explain what you are about to generate. "
        "Do NOT say 'Here are the questions:' or 'I will now create...'. "
        "Just output the content.\n"
        "4. Do NOT add sections or blocks not asked for.\n\n"

        "## ANSWER ACCURACY — MANDATORY\n\n"
        "1. Every MCQ must have exactly one unambiguously correct answer "
        "(unless it is explicitly a multiple-correct type).\n"
        "2. Every numerical answer must be computed step-by-step. "
        "Show every calculation. Final answer must match the shown working.\n"
        "3. Distractors (wrong options) must be plausible but definitively wrong. "
        "They should represent common mistakes — not random values.\n"
        "4. In every solution, clearly state the correct option "
        "(e.g. 'Correct Answer: (B)') followed by a full step-by-step explanation "
        "of exactly why that option is correct.\n"
        "5. Do NOT mark an answer correct if you cannot prove it from the source material.\n\n"

        "## LATEX RULES\n\n"
        "- Inline math: $expression$ — e.g. $v = u + at$\n"
        "- Display math: $$expression$$ — e.g. $$s = ut + \\frac{1}{2}at^2$$\n"
        "- Never leave a mathematical expression as plain text\n\n"

        "## GENERAL RULES\n\n"
        "- Follow all project instructions exactly\n"
        "- Output clean, well-structured markdown\n"
        "- Produce complete output — do not truncate or summarise\n\n"
        f"Project instructions:\n{system_instructions}"
    )


def _section_output_rules(start_q: int = 1) -> str:
    return (
        f"\nStructure your output with EXACTLY these two sections:\n\n"
        f"## QUESTIONS\n\n"
        f"[Questions numbered Q{start_q}, Q{start_q + 1}, Q{start_q + 2}, ...]\n\n"
        f"## SOLUTIONS\n\n"
        f"[Solutions: **Q{start_q}.** Answer: [answer] — [step-by-step explanation]]\n\n"
        "STRICT RULES:\n"
        f"- Question numbers MUST start from Q{start_q} — do NOT restart from Q1\n"
        "- Do NOT mix questions and solutions — keep sections completely separate\n"
        "- In ## SOLUTIONS: do NOT restate the question — only give the answer and explanation\n"
        "- Use LaTeX for all math: $inline$ and $$display block$$\n"
        "- Every question must have exactly one corresponding solution\n\n"
        "After ## SOLUTIONS, append this metadata block "
        "(it will be stripped and NOT appear in the Word document):\n\n"
        "---SECTION_META---\n"
        "Questions: Q[start]–Q[end] ([count] questions)\n"
        "Topics covered: [comma-separated list of main topics/concepts tested]\n"
        "Bloom's levels used: [level (Q range), ...]\n"
        "Key concepts tested: [specific formulas, laws, definitions used]\n"
        "Do NOT repeat in remaining sections: [specific concepts/question styles to avoid]\n"
        "---END_META---\n"
    )


def parse_section_output(raw_output: str) -> tuple[str, str]:
    """
    Split a section's raw AI output into:
      - clean_content: ## QUESTIONS + ## SOLUTIONS (goes into Word document)
      - metadata: the ---SECTION_META--- block (stripped from Word, passed to next sections)
    """
    meta_match = re.search(
        META_START + r"(.*?)" + META_END,
        raw_output, re.DOTALL | re.IGNORECASE,
    )
    if meta_match:
        metadata = meta_match.group(1).strip()
        before = raw_output[: meta_match.start()].strip()
        after = raw_output[meta_match.end() :].strip()
        clean_content = (before + "\n" + after).strip()
    else:
        clean_content = raw_output.strip()
        metadata = ""

    return clean_content, metadata


def parse_skeleton(output: str) -> tuple[str, list[dict]]:
    """
    Extract (document_header, sections_list) from skeleton output.
    Returns empty header and [] sections on parse failure.
    """
    header = ""
    sections: list[dict] = []

    # Extract document header
    header_match = re.search(
        HEADER_START + r"(.*?)" + HEADER_END,
        output, re.DOTALL | re.IGNORECASE,
    )
    if header_match:
        header = header_match.group(1).strip()
    else:
        logger.warning("No DOCUMENT_HEADER block found in skeleton output")
        # Fallback: use the whole output as header
        header = output.strip()

    # Extract JSON plan
    json_match = re.search(
        JSON_START + r"(.*?)" + JSON_END,
        output, re.DOTALL | re.IGNORECASE,
    )
    if not json_match:
        logger.error("No JSON_PLAN block found in skeleton output")
        return header, sections

    json_str = json_match.group(1).strip()
    # Strip markdown code fences if Claude wrapped the JSON
    json_str = re.sub(r"^```(?:json)?\s*\n?", "", json_str)
    json_str = re.sub(r"\n?```\s*$", "", json_str)

    try:
        data = json.loads(json_str)
        raw_sections = data.get("sections", [])
        # Validate and fill defaults for each section
        for i, s in enumerate(raw_sections):
            sections.append({
                "id": s.get("id") or f"section_{i + 1}",
                "title": s.get("title") or f"Section {i + 1}",
                "description": s.get("description") or "",
                "question_count": int(s.get("question_count") or 10),
                "marks_each": s.get("marks_each") or 4,
                "negative_marking": s.get("negative_marking"),   # None is valid here
                "question_format": s.get("question_format") or "",
                "bloom_levels": s.get("bloom_levels") or [],
                "special_instructions": s.get("special_instructions") or "",
            })
        if not sections:
            logger.error("Skeleton JSON parsed but sections list is empty")
        else:
            logger.info("Parsed %d sections from skeleton JSON", len(sections))

    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse skeleton JSON: %s | raw: %.300s", exc, json_str)

    return header, sections


# ─── Phase 1 ──────────────────────────────────────────────────────────────────

def source_audit(
    run_id: str, phase_name: str, context: dict[str, Any], provider: LLMProvider
) -> dict[str, Any]:
    """Audit source material — topics, difficulty, formulas, gaps."""
    user_prompt = (
        "Audit the source material above. Produce a structured report:\n"
        "1. **Key Topics** — all major concepts with brief descriptions\n"
        "2. **Difficulty Distribution** — easy/medium/hard proportions\n"
        "3. **Formula & Theory Coverage** — important formulas and theorems\n"
        "4. **Gaps & Recommendations** — what is missing for a complete worksheet\n\n"
        "Be thorough. This audit guides all subsequent generation."
    )
    result = provider.complete(
        system=_system_prompt(context.get("system_instructions", "")),
        source_text=context.get("source_text", ""),
        user_prompt=user_prompt,
        max_tokens=MAX_TOKENS,
    )
    logger.info("[%s] source_audit — in=%d out=%d cost=$%.4f",
                run_id, result.tokens_in, result.tokens_out, result.cost_usd)
    return {"output": result.text, "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out, "cost_usd": result.cost_usd,
            "prompt_sent": user_prompt}


# ─── Phase 2 ──────────────────────────────────────────────────────────────────

def worksheet_skeleton(
    run_id: str, phase_name: str, context: dict[str, Any], provider: LLMProvider
) -> dict[str, Any]:
    """
    Design the worksheet structure.

    Output contains TWO blocks:
    1. DOCUMENT_HEADER — premium Word cover page (markdown, goes into the .docx)
    2. JSON_PLAN       — machine-readable section definitions (drives generation phases)

    The sections in JSON_PLAN are entirely driven by system_instructions.
    """
    audit = context.get("phase_outputs", {}).get("source_audit", "")

    user_prompt = (
        f"Source Audit:\n{audit}\n\n"
        "Based on the source audit and your project instructions, design the complete worksheet.\n\n"
        "Output EXACTLY this two-block structure — no other text outside these blocks:\n\n"
        "---DOCUMENT_HEADER---\n"
        "[Premium academic cover page in clean markdown:\n"
        " - Worksheet title, subject, chapter\n"
        " - Exam type, duration, total marks\n"
        " - Section summary table: Section # | Type | Questions | Marks each | Total\n"
        " - Any general instructions for students]\n"
        "---END_HEADER---\n\n"
        "---JSON_PLAN---\n"
        "{\n"
        '  "sections": [\n'
        "    {\n"
        '      "id": "section_1",\n'
        '      "title": "Full section title as it appears in the document",\n'
        '      "description": "What this section tests and question type",\n'
        '      "question_count": <exact number>,\n'
        '      "marks_each": <marks per question>,\n'
        '      "negative_marking": <negative marks as negative number, or null>,\n'
        '      "question_format": "Detailed format description for the AI generator",\n'
        '      "bloom_levels": ["Level1", "Level2"],\n'
        '      "special_instructions": "Any special requirements from project instructions"\n'
        "    }\n"
        "  ],\n"
        '  "total_marks": <total>,\n'
        '  "duration_minutes": <minutes>\n'
        "}\n"
        "---END_JSON---\n\n"
        "CRITICAL:\n"
        "- Follow project instructions 100% for section types, counts, and formats\n"
        "- The sections in JSON must exactly match the DOCUMENT_HEADER table\n"
        "- Output ONLY the two blocks above — nothing else\n"
        "- The JSON must be valid — no trailing commas, no comments\n"
        "- Do NOT write actual questions — this is structure only"
    )
    result = provider.complete(
        system=_system_prompt(context.get("system_instructions", "")),
        source_text=context.get("source_text", ""),
        user_prompt=user_prompt,
        max_tokens=MAX_TOKENS,
    )
    logger.info("[%s] worksheet_skeleton — in=%d out=%d cost=$%.4f",
                run_id, result.tokens_in, result.tokens_out, result.cost_usd)
    return {"output": result.text, "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out, "cost_usd": result.cost_usd,
            "prompt_sent": user_prompt}


# ─── Dynamic section generator ────────────────────────────────────────────────

def generate_section(
    section_spec: dict,
    run_id: str,
    context: dict[str, Any],
    provider: LLMProvider,
) -> dict[str, Any]:
    """
    Generic section generator.

    Each call receives:
    - The full worksheet plan (document header) so Claude knows the overall structure
    - Metadata from all previously completed sections (topics covered, Q ranges, concepts to avoid)
    - This section's Q number range (pre-assigned so parallel sections don't overlap)
    - The section spec from JSON_PLAN

    Claude outputs section content + a ---SECTION_META--- block.
    The caller (orchestrator) strips the metadata block before storing in Word.
    """
    title = section_spec.get("title", "Section")
    description = section_spec.get("description", "")
    question_count = section_spec.get("question_count", 10)
    marks_each = section_spec.get("marks_each", 4)
    negative_marking = section_spec.get("negative_marking")
    question_format = section_spec.get("question_format", "")
    bloom_levels: list[str] = section_spec.get("bloom_levels", [])
    special_instructions = section_spec.get("special_instructions", "")

    # Q number range (pre-assigned in orchestrator to avoid overlaps in parallel runs)
    start_q: int = section_spec.get("start_question", 1)
    end_q: int = section_spec.get("end_question", start_q + question_count - 1)

    # Marks line
    marks_line = f"+{marks_each} per question"
    if negative_marking:
        marks_line += f", {negative_marking} negative marking"

    # Bloom's levels line
    bloom_line = (
        f"- Bloom's levels to cover: {', '.join(bloom_levels)}\n"
        if bloom_levels else ""
    )

    # Special instructions
    special_line = (
        f"\nSpecial instructions from project:\n{special_instructions}\n"
        if special_instructions else ""
    )

    # ── Worksheet context block (document header) ──────────────────────────
    document_header = context.get("document_header", "")
    worksheet_context = ""
    if document_header:
        worksheet_context = (
            "FULL WORKSHEET PLAN (for context — do not regenerate other sections):\n"
            f"{document_header}\n\n"
        )

    # ── Sections already generated (metadata only — not the actual questions) ──
    sections_metadata: list[str] = context.get("sections_metadata", [])
    prior_context = ""
    if sections_metadata:
        prior_context = (
            "SECTIONS ALREADY GENERATED — avoid repeating these topics/concepts:\n"
            + "\n".join(f"  {m}" for m in sections_metadata)
            + "\n\n"
        )

    prompt = (
        f"{worksheet_context}"
        f"{prior_context}"
        f"NOW GENERATE: **{title}**\n\n"
        f"Question range for this section: Q{start_q} to Q{end_q} "
        f"(continue numbering from previous sections — do NOT restart at Q1)\n\n"
        f"Section details:\n"
        f"- Description: {description}\n"
        f"- Marks: {marks_line}\n"
        f"- Question format: {question_format}\n"
        f"{bloom_line}"
        f"{special_line}"
        + _section_output_rules(start_q)
    )

    result = provider.complete(
        system=_system_prompt(context.get("system_instructions", "")),
        source_text=context.get("source_text", ""),
        user_prompt=prompt,
        max_tokens=MAX_TOKENS,
    )
    logger.info(
        "[%s] %s (Q%d–Q%d) — in=%d out=%d cost=$%.4f",
        run_id, section_spec.get("id"), start_q, end_q,
        result.tokens_in, result.tokens_out, result.cost_usd,
    )
    return {
        "output": result.text,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "cost_usd": result.cost_usd,
        "prompt_sent": prompt,
    }


# ─── Final assembly ───────────────────────────────────────────────────────────

def assemble_docx(
    run_id: str, context: dict[str, Any], provider: LLMProvider
) -> dict[str, Any]:
    """
    No AI call. Builds the final markdown document:
      [DOCUMENT_HEADER cover page]
      [Section 1 questions] ... [Section N questions]
      ---
      ## ANSWER KEY
      [Section 1 solutions] ... [Section N solutions]

    Sections are driven by context["sections"] (parsed from JSON_PLAN).
    Solutions do NOT restate question text (enforced in _section_output_rules).
    """
    sections: list[dict] = context.get("sections", [])
    phase_outputs = context.get("phase_outputs", {})
    document_header = context.get("document_header", "")

    question_blocks: list[str] = []
    solution_blocks: list[str] = []

    for section in sections:
        section_id = section["id"]
        section_title = section["title"]
        combined = phase_outputs.get(section_id, "")

        if not combined.strip():
            logger.warning("[%s] %s — no output, skipping from assembly", run_id, section_id)
            continue

        if QUESTIONS_MARKER in combined and SOLUTIONS_MARKER in combined:
            q_start = combined.index(QUESTIONS_MARKER)
            s_start = combined.index(SOLUTIONS_MARKER)
            questions = combined[q_start:s_start].strip()
            solutions = combined[s_start:].strip()
        else:
            questions = combined.strip()
            solutions = ""
            logger.warning("[%s] %s — section markers not found", run_id, section_id)

        question_blocks.append(f"### {section_title}\n\n{questions}")
        if solutions:
            solution_blocks.append(f"### {section_title}\n\n{solutions}")

    parts: list[str] = []
    if document_header.strip():
        parts.append(document_header.strip())
    if question_blocks:
        parts.append("\n\n".join(question_blocks))
    if solution_blocks:
        parts.append("---\n\n## ANSWER KEY\n\n" + "\n\n".join(solution_blocks))

    final_markdown = "\n\n".join(parts)
    logger.info("[%s] assemble_docx — %d chars, %d sections",
                run_id, len(final_markdown), len(question_blocks))
    return {"output": final_markdown, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
            "prompt_sent": "(no AI call — pure assembly of section outputs)"}
