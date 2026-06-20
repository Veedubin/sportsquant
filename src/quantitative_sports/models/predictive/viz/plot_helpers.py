from __future__ import annotations

from pathlib import Path

from matplotlib.figure import Figure


def finalize_figure(fig: Figure, *, output_path: Path | None) -> Figure:
    """Apply tight layout and optionally save a figure."""
    fig.tight_layout()
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
    return fig
