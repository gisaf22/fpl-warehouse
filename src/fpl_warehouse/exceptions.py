"""Named exceptions for the FPL warehouse build pipeline."""


class TeamResolutionError(Exception):
    """Raised when an Understat team name cannot be resolved to an FPL integer ID.

    This is a hard error — the build must halt rather than silently producing
    NULL fpl_id values in fact_match_stats.
    """
