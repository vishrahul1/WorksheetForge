import logging
import os
import re
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

REFERENCE_DOC_PATH = os.path.join(os.path.dirname(__file__), "reference.docx")

# Resolve pandoc binary — check PATH first, then common Windows install locations
def _find_pandoc() -> str:
    # 1. Check if pandoc is on PATH
    found = shutil.which("pandoc")
    if found:
        return found
    # 2. Common Windows install paths
    candidates = [
        r"C:\Program Files\Pandoc\pandoc.exe",
        r"C:\Program Files (x86)\Pandoc\pandoc.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Pandoc\pandoc.exe"),
        os.path.expandvars(r"%APPDATA%\Pandoc\pandoc.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            logger.info("Found pandoc at %s", path)
            return path
    raise FileNotFoundError(
        "Pandoc not found. Install from https://pandoc.org/installing.html "
        "and restart the worker."
    )

PANDOC_BIN = _find_pandoc()


def _strip_latex(markdown: str) -> str:
    """
    Fallback: replace LaTeX math with plain-text equivalents so Pandoc
    can still produce a DOCX when the math syntax is malformed.
    Display blocks ($$...$$) become indented text.
    Inline math ($...$) becomes the inner expression.
    """
    # Display math $$...$$
    markdown = re.sub(
        r"\$\$(.*?)\$\$",
        lambda m: f"\n[Math: {m.group(1).strip()}]\n",
        markdown,
        flags=re.DOTALL,
    )
    # Inline math $...$
    markdown = re.sub(
        r"\$([^$\n]+?)\$",
        lambda m: m.group(1).strip(),
        markdown,
    )
    # HTML comment markers (answer hints) that Pandoc sometimes chokes on
    markdown = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    return markdown


def _run_pandoc(md_path: str, docx_out: str, tmpdir: str) -> subprocess.CompletedProcess:
    cmd = [
        PANDOC_BIN,
        md_path,
        "--from=markdown+tex_math_dollars",
        "--to=docx",
        "--mathml",
        "-o",
        docx_out,
    ]
    if os.path.exists(REFERENCE_DOC_PATH):
        cmd += [f"--reference-doc={REFERENCE_DOC_PATH}"]

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=tmpdir,
        timeout=120,
    )


def assemble_docx(
    markdown_content: str,
    image_paths: list[str] | None = None,
    output_path: str | None = None,
) -> bytes:
    """
    Convert markdown (+LaTeX) to DOCX via Pandoc.
    Falls back to a LaTeX-stripped version if the first attempt fails.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, "input.md")
        docx_out = output_path or os.path.join(tmpdir, "output.docx")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        if image_paths:
            for img_path in image_paths:
                if os.path.exists(img_path):
                    shutil.copy(img_path, tmpdir)

        # Attempt 1 — full markdown with LaTeX
        logger.info("Pandoc attempt 1 (with LaTeX math)")
        result = _run_pandoc(md_path, docx_out, tmpdir)

        if result.returncode != 0:
            logger.warning(
                "Pandoc attempt 1 failed (exit %d): %s — retrying without LaTeX",
                result.returncode, result.stderr[:300],
            )

            # Attempt 2 — strip LaTeX and retry
            stripped = _strip_latex(markdown_content)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(stripped)

            logger.info("Pandoc attempt 2 (LaTeX stripped)")
            result = _run_pandoc(md_path, docx_out, tmpdir)

            if result.returncode != 0:
                logger.error("Pandoc attempt 2 stderr: %s", result.stderr)
                raise RuntimeError(
                    f"Pandoc failed on both attempts (exit {result.returncode}): "
                    f"{result.stderr[:500]}"
                )

            logger.info("Pandoc attempt 2 succeeded (LaTeX was stripped)")

        with open(docx_out, "rb") as f:
            return f.read()
