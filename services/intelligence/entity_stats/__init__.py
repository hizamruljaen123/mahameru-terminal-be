# entity_stats — Modular Multi-Method Statistical Testing Engine
# Each module returns: { "stats": [...], "charts": {...}, "summary": "..." }

from .normality import compute_normality
from .stationarity import compute_stationarity
from .autocorrelation import compute_autocorrelation
from .distribution import compute_distribution
from .descriptive import compute_descriptive
from .variance import compute_variance
from .correlation import compute_correlation

__all__ = [
    "compute_normality",
    "compute_stationarity",
    "compute_autocorrelation",
    "compute_distribution",
    "compute_descriptive",
    "compute_variance",
    "compute_correlation",
]
