"""RC and long-note difficulty on the pinned SPM Rating candidate."""
import sys
from pathlib import Path

_upstream = Path(__file__).resolve().parent.parent / 'SPMRating'
if str(_upstream) not in sys.path:
    sys.path.insert(0, str(_upstream))
from .engine import rate_content, rate_file, rate_notes

__all__ = ["rate_content", "rate_file", "rate_notes"]
