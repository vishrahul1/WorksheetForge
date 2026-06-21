import io
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


def docx_to_html(docx_bytes: bytes) -> str:
    """Convert DOCX bytes to HTML using mammoth."""
    import mammoth

    with io.BytesIO(docx_bytes) as f:
        result = mammoth.convert_to_html(f)
        if result.messages:
            for msg in result.messages:
                logger.warning("mammoth: %s", msg)
        return result.value


def html_to_docx(html_content: str) -> bytes:
    """Convert HTML back to DOCX via Pandoc (HTML -> markdown -> docx pipeline)."""
    from app.services.pandoc import assemble_docx

    # Convert HTML to markdown via pandoc, then to docx
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "input.html")
        md_path = os.path.join(tmpdir, "intermediate.md")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        import subprocess

        result = subprocess.run(
            ["pandoc", html_path, "--from=html", "--to=markdown", "-o", md_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Pandoc HTML->MD failed: {result.stderr[:300]}")

        with open(md_path, "r", encoding="utf-8") as f:
            markdown = f.read()

    return assemble_docx(markdown)
