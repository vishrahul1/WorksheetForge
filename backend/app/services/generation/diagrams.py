"""
Matplotlib diagram helpers for worksheet generation.
Generates PNG images from diagram specifications embedded in AI output.
"""
import io
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)


def render_matplotlib_block(code: str, output_dir: str) -> str | None:
    """
    Execute a matplotlib code block and save the resulting figure as PNG.
    Returns the path to the saved PNG, or None on failure.
    """
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt

    try:
        fig_path = os.path.join(output_dir, f"diagram_{abs(hash(code))}.png")
        exec_globals: dict = {"plt": plt}
        exec(code, exec_globals)  # noqa: S102
        plt.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close("all")
        logger.info("Rendered diagram to %s", fig_path)
        return fig_path
    except Exception as exc:
        logger.warning("Failed to render diagram: %s", exc)
        plt.close("all")
        return None


def extract_and_render_diagrams(markdown_content: str, output_dir: str) -> tuple[str, list[str]]:
    """
    Find ```python-diagram ... ``` blocks in markdown, render them,
    and replace with ![diagram](path) references.

    Returns: (updated_markdown, list_of_image_paths)
    """
    pattern = re.compile(r"```python-diagram\n(.*?)```", re.DOTALL)
    image_paths: list[str] = []
    counter = [0]

    def replace_block(match: re.Match) -> str:
        code = match.group(1)
        img_path = render_matplotlib_block(code, output_dir)
        if img_path:
            image_paths.append(img_path)
            counter[0] += 1
            return f"![Diagram {counter[0]}]({os.path.basename(img_path)})"
        return ""

    updated = pattern.sub(replace_block, markdown_content)
    return updated, image_paths
