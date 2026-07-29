"""Point-in-time joins and revision-safe selection helpers."""

from __future__ import annotations

import pandas as pd


def select_latest_available(
    frame: pd.DataFrame,
    issue_time: pd.Timestamp,
    delivery_columns: list[str],
    published_column: str = "published_at_utc",
) -> pd.DataFrame:
    """Select the latest revision available by ``issue_time`` for each delivery key."""
    if published_column not in frame:
        raise KeyError(f"Missing publication timestamp column: {published_column}")
    missing = [column for column in delivery_columns if column not in frame]
    if missing:
        raise KeyError(f"Missing delivery key columns: {missing}")

    issue = pd.Timestamp(issue_time)
    if issue.tzinfo is None:
        issue = issue.tz_localize("UTC")
    else:
        issue = issue.tz_convert("UTC")

    out = frame.copy()
    out[published_column] = pd.to_datetime(out[published_column], utc=True, errors="coerce")
    out = out.loc[out[published_column].le(issue)].dropna(subset=[published_column])
    return (
        out.sort_values(published_column)
        .drop_duplicates(subset=delivery_columns, keep="last")
        .sort_values(delivery_columns)
        .reset_index(drop=True)
    )


def asof_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    issue_column: str,
    published_column: str,
    by: list[str],
    suffix: str,
) -> pd.DataFrame:
    """Join each forecast row to the latest source revision available at issue time."""
    lhs = left.copy()
    rhs = right.copy()
    lhs[issue_column] = pd.to_datetime(lhs[issue_column], utc=True)
    rhs[published_column] = pd.to_datetime(rhs[published_column], utc=True)
    lhs = lhs.sort_values([*by, issue_column])
    rhs = rhs.sort_values([*by, published_column])
    return pd.merge_asof(
        lhs,
        rhs,
        left_on=issue_column,
        right_on=published_column,
        by=by,
        direction="backward",
        suffixes=("", suffix),
    )


def require_no_future_information(
    frame: pd.DataFrame,
    issue_column: str = "issue_time_utc",
    publication_columns: list[str] | None = None,
) -> None:
    """Raise when any selected feature revision was published after forecast issue."""
    publication_columns = publication_columns or [
        column for column in frame if column.endswith("published_at_utc")
    ]
    issue = pd.to_datetime(frame[issue_column], utc=True)
    violations: dict[str, int] = {}
    for column in publication_columns:
        published = pd.to_datetime(frame[column], utc=True, errors="coerce")
        count = int((published > issue).fillna(False).sum())
        if count:
            violations[column] = count
    if violations:
        raise ValueError(f"Future-information leakage detected: {violations}")
