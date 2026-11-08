"""Ligas de pontos corridos locais, sem dependências de runtime."""

from .engine import (
    LeagueError,
    clear_result,
    create_league,
    dumps_league,
    fixtures,
    import_results_csv,
    loads_league,
    progress,
    results_csv,
    set_result,
    standings,
    standings_csv,
    validate_league,
)

__all__ = [
    "LeagueError", "create_league", "validate_league", "set_result", "clear_result",
    "standings", "progress", "fixtures", "dumps_league", "loads_league",
    "import_results_csv", "results_csv", "standings_csv",
]
