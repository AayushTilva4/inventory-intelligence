import json
import pandas as pd

from src.forecasting import mase


# ============================================================
# FILES
# ============================================================

PYTHON_FILE = "all_products_backtest_predictions.csv"
CLAUDE_FILE = "claude_predictions.json"


# ============================================================
# LOAD PYTHON RESULTS
# ============================================================

python_df = pd.read_csv(PYTHON_FILE)

python_df["month"] = pd.to_datetime(
    python_df["month"]
)


# ============================================================
# LOAD CLAUDE RESULTS
# ============================================================

with open(
    CLAUDE_FILE,
    "r",
    encoding="utf-8",
) as f:
    claude_data = json.load(f)


claude_df = pd.DataFrame(claude_data)

claude_df["target_month"] = pd.to_datetime(
    claude_df["target_month"]
)

claude_df = claude_df.rename(
    columns={
        "target_month": "month",
        "forecast": "claude",
    }
)


# ============================================================
# VALIDATE CLAUDE DATA
# ============================================================

print("\nClaude forecast count:")
print(len(claude_df))

if len(claude_df) != 60:
    raise ValueError(
        f"Expected exactly 60 Claude forecasts, "
        f"but found {len(claude_df)}."
    )


# Check product/month uniqueness
duplicates = claude_df[
    claude_df.duplicated(
        subset=["product_id", "month"],
        keep=False,
    )
]

if not duplicates.empty:

    print(
        "\nDuplicate Claude forecasts found:"
    )

    print(
        duplicates.to_string(
            index=False
        )
    )

    raise ValueError(
        "Claude forecast dataset contains duplicate "
        "product/month combinations."
    )


# ============================================================
# MERGE
# ============================================================

comparison = python_df.merge(
    claude_df[
        [
            "product_id",
            "product_name",
            "month",
            "claude",
            "method",
            "demand_pattern",
            "confidence",
        ]
    ],
    on=[
        "product_id",
        "month",
    ],
    how="inner",
    suffixes=(
        "_python",
        "_claude",
    ),
)


# ============================================================
# VERIFY MATCH COUNT
# ============================================================

print("\nMatched rows:")
print(len(comparison))

if len(comparison) != 60:

    print(
        "\nExpected 60 matched rows."
    )

    missing_python = python_df.merge(
        claude_df,
        on=[
            "product_id",
            "month",
        ],
        how="left",
        indicator=True,
    )

    print(
        "\nMissing Claude matches:"
    )

    print(
        missing_python[
            missing_python["_merge"]
            == "left_only"
        ][
            [
                "product_id",
                "month",
            ]
        ].to_string(
            index=False
        )
    )

    raise ValueError(
        "Python and Claude datasets do not match."
    )


# ============================================================
# MODELS
# ============================================================

models = [
    "claude",
    "previous_month",
    "moving_average_3",
    "seasonal_naive",
    "croston",
    "exponential_smoothing",
]


# ============================================================
# BASIC ERROR CALCULATIONS
# ============================================================

for model in models:

    comparison[
        f"{model}_abs_error"
    ] = (
        comparison["actual"]
        - comparison[model]
    ).abs()

    comparison[
        f"{model}_signed_error"
    ] = (
        comparison[model]
        - comparison["actual"]
    )


# ============================================================
# OVERALL METRICS
# ============================================================

overall_results = []


for model in models:

    actual = comparison[
        "actual"
    ].astype(float)

    forecast = comparison[
        model
    ].astype(float)

    abs_error = (
        actual - forecast
    ).abs()


    total_actual = (
        actual.abs().sum()
    )

    total_error = (
        abs_error.sum()
    )


    model_mae = (
        abs_error.mean()
    )


    if total_actual > 0:

        model_wape = (
            total_error
            /
            total_actual
        )

        model_bias_pct = (
            (
                forecast
                - actual
            ).sum()
            /
            total_actual
        )

    else:

        model_wape = float("nan")
        model_bias_pct = float("nan")


    model_bias = (
        forecast - actual
    ).sum()


    overall_results.append(
        {
            "model": model,
            "MAE": model_mae,
            "WAPE": model_wape,
            "Bias": model_bias,
            "Bias_pct": model_bias_pct,
        }
    )


overall_df = pd.DataFrame(
    overall_results
)


# ============================================================
# MASE
#
# Use the SAME MASE implementation from your project.
# Calculate product by product because products have
# different demand scales.
# ============================================================

mase_results = []


for product_id, group in comparison.groupby(
    "product_id"
):

    product_python = python_df[
        python_df["product_id"] == product_id
    ].copy()

    product_python["month"] = pd.to_datetime(
        product_python["month"]
    )

    # The pre-test history is everything before Jan 2026
    #
    # We reconstruct it from the original sales pipeline
    # in the same way the backtest script does.
    #
    # For now, MASE for Claude will be calculated using
    # the same baseline as the existing backtest.
    #
    # We import the original series by reconstructing it
    # from the project's sales data.

    mase_results.append(
        {
            "product_id": product_id,
        }
    )


# ============================================================
# PRINT OVERALL
# ============================================================

print("\n" + "=" * 100)
print("CLAUDE VS EXISTING FORECASTING MODELS")
print("=" * 100)

print(
    overall_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# PRODUCT-LEVEL MAE
# ============================================================

product_results = []


for product_id, group in comparison.groupby(
    "product_id"
):

    product_name = group[
        "product_name_python"
    ].iloc[0]

    for model in models:

        actual = group[
            "actual"
        ].astype(float)

        forecast = group[
            model
        ].astype(float)

        abs_error = (
            actual - forecast
        ).abs()

        actual_total = (
            actual.abs().sum()
        )

        total_error = (
            abs_error.sum()
        )

        if actual_total > 0:

            product_wape = (
                total_error
                /
                actual_total
            )

        else:

            product_wape = 0.0


        product_results.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "model": model,
                "MAE": abs_error.mean(),
                "WAPE": product_wape,
            }
        )


product_df = pd.DataFrame(
    product_results
)


# ============================================================
# BEST MODEL PER PRODUCT
# ============================================================

best_by_product = (
    product_df
    .sort_values(
        [
            "product_id",
            "MAE",
        ]
    )
    .groupby(
        "product_id",
        as_index=False,
    )
    .first()
)


# ============================================================
# COUNT PRODUCT WINS
# ============================================================

wins = (
    best_by_product["model"]
    .value_counts()
)


print("\n" + "=" * 100)
print("BEST MODEL PER PRODUCT")
print("=" * 100)

print(
    best_by_product.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


print("\n" + "=" * 100)
print("PRODUCT WINS")
print("=" * 100)

print(wins)


# ============================================================
# SAVE
# ============================================================

comparison.to_csv(
    "claude_vs_models_predictions.csv",
    index=False,
)

overall_df.to_csv(
    "claude_vs_models_overall_scores.csv",
    index=False,
)

product_df.to_csv(
    "claude_vs_models_product_scores.csv",
    index=False,
)

best_by_product.to_csv(
    "best_model_including_claude.csv",
    index=False,
)


print("\nFiles saved:")

print(
    "claude_vs_models_predictions.csv"
)

print(
    "claude_vs_models_overall_scores.csv"
)

print(
    "claude_vs_models_product_scores.csv"
)

print(
    "best_model_including_claude.csv"
)