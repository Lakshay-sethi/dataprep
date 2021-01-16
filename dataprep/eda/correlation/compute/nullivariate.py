"""Implementations of correlations.

Currently this boils down to pandas' implementation."""

from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import dask
import dask.dataframe as dd
import numpy as np
import pandas as pd

from ...configs import Config
from ...data_array import DataArray
from ...intermediate import Intermediate
from ...utils import cut_long_name
from .common import CorrelationMethod


def _calc_nullivariate(
    df: dd.DataFrame,
    cfg: Config,
    *,
    value_range: Optional[Tuple[float, float]] = None,
    k: Optional[int] = None,
) -> Intermediate:
    # pylint: disable=too-many-statements,too-many-locals,too-many-branches

    # most_show = 6  # the most number of column/row to show in "insight"

    if value_range is not None and k is not None:
        raise ValueError("value_range and k cannot be present in both")

    (corrs,) = dask.compute(correlation_nxn(df, cfg))

    # The computations below is not expensive (scales with # of columns)
    # So we do them in pandas

    # if cfg.stats.enable or cfg.insight.enable:
    #     if cfg.stats.enable or cfg.pearson.enable:
    #         (
    #             pearson_pos_max,
    #             pearson_neg_max,
    #             pearson_mean,
    #             pearson_pos_cols,
    #             pearson_neg_cols,
    #         ) = most_corr(corrs[CorrelationMethod.Pearson])
    #         pearson_min, pearson_cols = least_corr(corrs[CorrelationMethod.Pearson])
    #     if cfg.stats.enable or cfg.spearman.enable:
    #         (
    #             spearman_pos_max,
    #             spearman_neg_max,
    #             spearman_mean,
    #             spearman_pos_cols,
    #             spearman_neg_cols,
    #         ) = most_corr(corrs[CorrelationMethod.Spearman])
    #         spearman_min, spearman_cols = least_corr(corrs[CorrelationMethod.Spearman])
    #     if cfg.stats.enable or cfg.kendall.enable:
    #         (
    #             kendalltau_pos_max,
    #             kendalltau_neg_max,
    #             kendalltau_mean,
    #             kendalltau_pos_cols,
    #             kendalltau_neg_cols,
    #         ) = most_corr(corrs[CorrelationMethod.KendallTau])
    #         kendalltau_min, kendalltau_cols = least_corr(corrs[CorrelationMethod.KendallTau])

    # if cfg.stats.enable:
    #     tabledata = {
    #         "Highest Positive Correlation": {
    #             "Pearson": pearson_pos_max,
    #             "Spearman": spearman_pos_max,
    #             "KendallTau": kendalltau_pos_max,
    #         },
    #         "Highest Negative Correlation": {
    #             "Pearson": pearson_neg_max,
    #             "Spearman": spearman_neg_max,
    #             "KendallTau": kendalltau_neg_max,
    #         },
    #         "Lowest Correlation": {
    #             "Pearson": pearson_min,
    #             "Spearman": spearman_min,
    #             "KendallTau": kendalltau_min,
    #         },
    #         "Mean Correlation": {
    #             "Pearson": pearson_mean,
    #             "Spearman": spearman_mean,
    #             "KendallTau": kendalltau_mean,
    #         },
    #     }

    # if cfg.insight.enable:
    #     insights: Dict[str, List[Any]] = {}
    #     if cfg.pearson.enable:
    #         p_p_corr = create_string("positive", pearson_pos_cols, most_show, df)
    #         p_n_corr = create_string("negative", pearson_neg_cols, most_show, df)
    #         p_corr = create_string("least", pearson_cols, most_show, df)
    #         insights["Pearson"] = [p_p_corr, p_n_corr, p_corr]
    #     if cfg.spearman.enable:
    #         s_p_corr = create_string("positive", spearman_pos_cols, most_show, df)
    #         s_n_corr = create_string("negative", spearman_neg_cols, most_show, df)
    #         s_corr = create_string("least", spearman_cols, most_show, df)
    #         insights["Spearman"] = [s_p_corr, s_n_corr, s_corr]
    #     if cfg.kendall.enable:
    #         k_p_corr = create_string("positive", kendalltau_pos_cols, most_show, df)
    #         k_n_corr = create_string("negative", kendalltau_neg_cols, most_show, df)
    #         k_corr = create_string("least", kendalltau_cols, most_show, df)
    #         insights["KendallTau"] = [k_p_corr, k_n_corr, k_corr]

    dfs = {}
    for method, corr in corrs.items():
        if (  # pylint: disable=too-many-boolean-expressions
            method == CorrelationMethod.Pearson
            and not cfg.pearson.enable
            or method == CorrelationMethod.Spearman
            and not cfg.spearman.enable
            or method == CorrelationMethod.KendallTau
            and not cfg.kendall.enable
        ):
            continue

        ndf = pd.DataFrame({"correlation": [x.loc[0] for x in corr]})
        ndf[["x", "y"]] = list(combinations(df.columns, 2))

        if k is not None:
            thresh = ndf["correlation"].abs().nlargest(k).iloc[-1]
            ndf = ndf[(ndf["correlation"] >= thresh) | (ndf["correlation"] <= -thresh)]
        elif value_range is not None:
            mask = (value_range[0] <= ndf["correlation"]) & (ndf["correlation"] <= value_range[1])
            ndf = ndf[mask]

        dfs[method.name] = ndf

    return Intermediate(
        data=dfs,
        axis_range=list(df.columns.unique()),
        visual_type="correlation_impact",
        tabledata={},  # tabledata if cfg.stats.enable else {},
        insights={},  # insights if cfg.insight.enable else {},
    )


def correlation_nxn(df: DataArray, cfg: Config) -> Dict[CorrelationMethod, Any]:
    """
    Calculation of a n x n correlation matrix for n columns

    Returns
    -------
        The long format of the correlations
    """
    corrs: Dict[CorrelationMethod, Any] = {}

    if cfg.pearson.enable or cfg.stats.enable:
        corrs[CorrelationMethod.Pearson] = _pearson_nxn(df)
    if cfg.spearman.enable or cfg.stats.enable:
        corrs[CorrelationMethod.Spearman] = _spearman_nxn(df)
    if cfg.kendall.enable or cfg.stats.enable:
        corrs[CorrelationMethod.KendallTau] = _kendall_tau_nxn(df)

    return corrs


def _corr(df: pd.DataFrame, x: str, y: str, method: str) -> pd.Series:
    """Pandas correlation between two Series."""
    return df[x].corr(df[y], method=method)


def _pearson_nxn(df: dd.DataFrame) -> Any:
    """Calculate column-wise pearson correlation."""
    return [
        df.repartition(1).map_partitions(_corr, x, y, "pearson")
        for x, y in combinations(df.columns, 2)
    ]


def _spearman_nxn(df: dd.DataFrame) -> Any:
    """Calculate column-wise spearman correlation."""
    return [
        df.repartition(1).map_partitions(_corr, x, y, "spearman")
        for x, y in combinations(df.columns, 2)
    ]


def _kendall_tau_nxn(df: dd.DataFrame) -> Any:
    """Calculate column-wise kendalltau correlation."""
    return [
        df.repartition(1).map_partitions(_corr, x, y, "kendall")
        for x, y in combinations(df.columns, 2)
    ]


def most_corr(corrs: np.ndarray) -> Tuple[float, float, float, List[Any], List[Any]]:
    """Find the most correlated columns."""
    positive_col_set = set()
    negative_col_set = set()
    corrs_copy = corrs
    for i in range(corrs_copy.shape[0]):
        corrs_copy[i, i] = 0
    mean = corrs_copy.mean()
    p_maximum = corrs_copy.max()
    n_maximum = (-corrs_copy).max()

    if p_maximum != 0:
        p_col1, p_col2 = np.where(corrs_copy == p_maximum)
    else:
        p_col1, p_col2 = [], []
    if n_maximum != 0:
        n_col1, n_col2 = np.where(corrs_copy == -n_maximum)
    else:
        n_col1, n_col2 = [], []

    for i, _ in enumerate(p_col1):
        if p_col1[i] < p_col2[i]:
            positive_col_set.add((p_col1[i], p_col2[i]))
        elif p_col1[i] > p_col2[i]:
            positive_col_set.add((p_col2[i], p_col1[i]))
    for i, _ in enumerate(n_col1):
        if n_col1[i] < n_col2[i]:
            negative_col_set.add((n_col1[i], n_col2[i]))
        elif n_col1[i] > n_col2[i]:
            negative_col_set.add((n_col2[i], n_col1[i]))

    return (
        round(p_maximum, 3),
        round(-n_maximum, 3),
        round(mean, 3),
        list(positive_col_set),
        list(negative_col_set),
    )


def least_corr(corrs: np.ndarray) -> Tuple[float, List[Any]]:
    """Find the least correlated columns."""
    col_set = set()
    corrs_copy = corrs
    for i in range(corrs_copy.shape[0]):
        corrs_copy[i, i] = 2
    minimum = abs(corrs_copy).min()
    col1, col2 = np.where(corrs_copy == minimum)

    for i, _ in enumerate(col1):
        if col1[i] < col2[i]:
            col_set.add((col1[i], col2[i]))
        elif col1[i] > col2[i]:
            col_set.add((col2[i], col1[i]))

    return round(minimum, 3), list(col_set)


def create_string(flag: str, source: List[Any], most_show: int, df: DataArray) -> str:
    """Create the output string"""
    suffix = "" if len(source) <= most_show else ", ..."
    if flag == "positive":
        prefix = "Most positive correlated: "
        temp = "Most positive correlated: None"
    elif flag == "negative":
        prefix = "Most negative correlated: "
        temp = "Most negative correlated: None"
    elif flag == "least":
        prefix = "Least correlated: "
        temp = "Least correlated: None"

    if source != []:
        out = (
            prefix
            + ", ".join(
                "(" + cut_long_name(df.columns[e[0]]) + ", " + cut_long_name(df.columns[e[1]]) + ")"
                for e in source[:most_show]
            )
            + suffix
        )
    else:
        out = temp

    return out


## The code below is the correlation algorithms for array. Since we don't have
## block-wise algorithms for spearman and kendalltal, it might be more suitable
## to just use the pandas version of correlation.
## The correlations from pandas use double for-loops but they write them in cython
## and they are super fast already.
#
# def _pearson_nxn(data: da.Array) -> da.Array:
#     """Calculate column-wise pearson correlation."""

#     mean = data.mean(axis=0)[None, :]
#     dem = data - mean

#     num = dem.T @ dem

#     std = data.std(axis=0, keepdims=True)
#     dom = data.shape[0] * (std * std.T)

#     correl = num / dom

#     return correl


# def _spearman_nxn(array: da.Array) -> da.Array:
#     rank_array = (
#         array.rechunk((-1, None))  #! TODO: avoid this
#         .map_blocks(partial(rankdata, axis=0))
#         .rechunk("auto")
#     )
#     return _pearson_nxn(rank_array)


# def _kendall_tau_nxn(array: da.Array) -> da.Array:
#     """Kendal Tau correlation outputs an n x n correlation matrix for n columns."""

#     _, ncols = array.shape

#     corrmat = []
#     for _ in range(ncols):
#         corrmat.append([float("nan")] * ncols)

#     for i in range(ncols):
#         corrmat[i][i] = 1.0

#     for i in range(ncols):
#         for j in range(i + 1, ncols):

#             tmp = kendalltau(array[:, i], array[:, j])

#             corrmat[j][i] = corrmat[i][j] = da.from_delayed(
#                 tmp, shape=(), dtype=np.float
#             )

#     return da.stack(corrmat)
