"""Documentation route for the SportsQuant web UI.

Renders the project README as HTML and lists available doc files
from the docs/ directory for easy navigation.
"""

from __future__ import annotations

from pathlib import Path

import markdown
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

# Find the project root (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
README_PATH = PROJECT_ROOT / "README.md"
DOCS_DIR = PROJECT_ROOT / "docs"


@router.get("/docs", response_class=HTMLResponse)
async def docs_index(request: Request) -> HTMLResponse:
    """Render the docs page showing the README and a sidebar of doc files."""
    # Read and convert README.md to HTML
    readme_md = ""
    if README_PATH.exists():
        readme_md = README_PATH.read_text(encoding="utf-8")

    readme_html = markdown.markdown(
        readme_md,
        extensions=["fenced_code", "tables", "toc", "codehilite"],
    )

    # List available doc files from docs/
    doc_files: list[dict[str, str]] = []
    if DOCS_DIR.exists():
        for p in sorted(DOCS_DIR.glob("*.md")):
            doc_files.append({"name": p.stem, "path": p.name})

    return request.app.state.templates.TemplateResponse(
        request,
        "docs.html",
        {"request": request, "readme_html": readme_html, "doc_files": doc_files},
        )
