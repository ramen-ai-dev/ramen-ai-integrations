"""ramen-ai filtration for RAG ingestion and MLOps datasets."""

from .filter import (
    FiltrationError,
    FiltrationMode,
    FiltrationResult,
    filter_csv,
    filter_dataframe,
)

__all__ = [
    "FiltrationError",
    "FiltrationMode",
    "FiltrationResult",
    "filter_csv",
    "filter_dataframe",
]
__version__ = "0.1.1"
