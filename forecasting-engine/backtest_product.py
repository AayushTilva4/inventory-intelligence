import pandas as pd

from src.sales_data import (
    fetch_sales_data,
    create_monthly_sales,
    complete_product_series,
)

from src.forecasting import (
    previous_month_forecast,
    moving_average_forecast,
    seasonal_naive_forecast,
    croston_forecast,
    exponential_smoothing_forecast,
    mae,
    wape,
    mase,
)


# ============================================================
# SETTINGS
# ============================================================

PRODUCT_IDS = [
    14,
    15,
    120,
    125,
    139,
    143,
    177,
    195,
    197,
    225,
]

TEST_START = "2026-01-01"
TEST_END = "2026-06-01"
HISTORY_START = "2023-08-01"

SEASON_LENGTH = 12


# ============================================================
# LOAD DATA
# ============================================================

print("Fetching sales data...")

sales_df = fetch_sales_data()
monthly_df = create_monthly_sales(sales_df)


# ============================================================
# STORAGE
# ============================================================

all_results = []
product_scores = []


# ============================================================
# PROCESS PRODUCTS
# ============================================================

for product_id in PRODUCT_IDS:

    print("\n" + "=" * 90)
    print(f"Processing product ID: {product_id}")
    print("=" * 90)

    # --------------------------------------------------------
    # Get product data
    # --------------------------------------------------------

    product_df = monthly_df[
        monthly_df["product_id"] == product_id
    ].copy()

    if product_df.empty:
        print(f"Product {product_id} not found.")
        continue

    # --------------------------------------------------------
    # Normalize dates
    # --------------------------------------------------------

    product_df["month"] = pd.to_datetime(
        product_df["month"]
    )

    product_df = (
        product_df
        .sort_values("month")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Product name
    # --------------------------------------------------------

    if (
        "product_name" in product_df.columns
        and not product_df["product_name"].dropna().empty
    ):
        product_name = (
            product_df["product_name"]
            .dropna()
            .iloc[0]
        )
    else:
        product_name = str(product_id)

    # --------------------------------------------------------
    # Determine first historical month
    # --------------------------------------------------------

    first_month = product_df["month"].min()

    # Product needs historical data before test period.
    if first_month > pd.Timestamp(TEST_START):

        print(
            f"Skipping {product_id}: "
            f"no historical demand before {TEST_START}."
        )

        continue

    # --------------------------------------------------------
    # Restrict historical window
    # --------------------------------------------------------

    product_df = product_df[
        product_df["month"] >= pd.Timestamp(HISTORY_START)
    ].copy()

    product_df = product_df.reset_index(drop=True)

    if product_df.empty:
        print(
            f"Skipping {product_id}: "
            "no history after HISTORY_START."
        )
        continue

    # --------------------------------------------------------
    # IMPORTANT:
    # Build an explicit continuous monthly series through
    # the end of the test period.
    #
    # Missing months are treated as zero demand.
    # --------------------------------------------------------

    product_df = (
        product_df
        .set_index("month")
        .sort_index()
    )

    full_months = pd.date_range(
        start=pd.Timestamp(HISTORY_START),
        end=pd.Timestamp(TEST_END),
        freq="MS",
    )

    # Preserve product-level metadata
    product_df = product_df.reindex(
        full_months
    )

    product_df.index.name = "month"

    product_df["product_id"] = product_id
    product_df["product_name"] = product_name

    # Missing monthly demand = zero
    product_df["total_quantity"] = (
        product_df["total_quantity"]
        .fillna(0.0)
        .astype(float)
    )

    product_df = (
        product_df
        .reset_index()
        .rename(columns={"index": "month"})
    )

    # --------------------------------------------------------
    # Verify enough history
    # --------------------------------------------------------

    pre_test_mask = (
        product_df["month"]
        < pd.Timestamp(TEST_START)
    )

    pre_test_data = product_df[
        pre_test_mask
    ]

    if len(pre_test_data) < 6:

        print(
            f"Skipping {product_id}: "
            "less than 6 historical months before "
            "the test period."
        )

        continue

    # --------------------------------------------------------
    # Sales series
    # --------------------------------------------------------

    sales = (
        product_df["total_quantity"]
        .astype(float)
        .reset_index(drop=True)
    )

    print(f"Product: {product_name}")
    print(f"Product ID: {product_id}")

    print(
        "History used:",
        product_df["month"].min(),
        "to",
        product_df["month"].max(),
    )


    # ========================================================
    # TEST MONTHS
    # ========================================================

    test_mask = (
        (product_df["month"] >= pd.Timestamp(TEST_START))
        & (product_df["month"] <= pd.Timestamp(TEST_END))
    )

    test_indices = product_df.index[
        test_mask
    ].tolist()

    expected_months = list(
        pd.date_range(
            TEST_START,
            TEST_END,
            freq="MS",
        )
    )

    actual_test_months = product_df.loc[
        test_indices,
        "month",
    ].tolist()

    if actual_test_months != expected_months:

        print(
            f"Skipping {product_id}: "
            "test months could not be constructed."
        )

        print(
            "Expected:",
            expected_months,
        )

        print(
            "Found:",
            actual_test_months,
        )

        continue


    # ========================================================
    # WALK-FORWARD BACKTEST
    # ========================================================

    product_results = []

    for i in test_indices:

        target_month = product_df.loc[
            i,
            "month",
        ]

        actual = float(
            sales.iloc[i]
        )

        # ----------------------------------------------------
        # Only information available BEFORE target month
        # ----------------------------------------------------

        train = sales.iloc[:i].copy()

        # ----------------------------------------------------
        # Forecasts
        # ----------------------------------------------------

        previous = previous_month_forecast(
            train
        )

        moving_avg = moving_average_forecast(
            train,
            window=3,
        )

        seasonal = seasonal_naive_forecast(
            train,
            season_length=SEASON_LENGTH,
        )

        croston = croston_forecast(
            train
        )

        exponential = exponential_smoothing_forecast(
            train,
            seasonal_periods=SEASON_LENGTH,
        )

        result = {
            "product_id": product_id,
            "product_name": product_name,
            "month": target_month,
            "actual": actual,
            "previous_month": previous,
            "moving_average_3": moving_avg,
            "seasonal_naive": seasonal,
            "croston": croston,
            "exponential_smoothing": exponential,
        }

        product_results.append(result)
        all_results.append(result)


    # ========================================================
    # PRODUCT METRICS
    # ========================================================

    product_results_df = pd.DataFrame(
        product_results
    )

    models = [
        "previous_month",
        "moving_average_3",
        "seasonal_naive",
        "croston",
        "exponential_smoothing",
    ]

    pre_test_sales = sales.iloc[
        :test_indices[0]
    ]

    for model in models:

        model_mae = mae(
            product_results_df["actual"],
            product_results_df[model],
        )

        model_wape = wape(
            product_results_df["actual"],
            product_results_df[model],
        )

        try:

            model_mase = mase(
                product_results_df["actual"],
                product_results_df[model],
                pre_test_sales,
                season_length=SEASON_LENGTH,
            )

        except Exception:

            model_mase = float("nan")

        product_scores.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "model": model,
                "MAE": model_mae,
                "WAPE": model_wape,
                "MASE": model_mase,
            }
        )


# ============================================================
# DATAFRAMES
# ============================================================

results_df = pd.DataFrame(
    all_results
)

scores_df = pd.DataFrame(
    product_scores
)


if results_df.empty:

    raise ValueError(
        "No products produced valid backtest results."
    )


# ============================================================
# ALL FORECASTS
# ============================================================

print("\n" + "=" * 110)
print(
    "ALL PRODUCT WALK-FORWARD FORECASTS"
)
print("=" * 110)

print(
    results_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# PRODUCT-LEVEL PERFORMANCE
# ============================================================

print("\n" + "=" * 110)
print(
    "PRODUCT-LEVEL MODEL PERFORMANCE"
)
print("=" * 110)

print(
    scores_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# OVERALL PERFORMANCE
# ============================================================

models = [
    "previous_month",
    "moving_average_3",
    "seasonal_naive",
    "croston",
    "exponential_smoothing",
]


overall_scores = []

for model in models:

    model_mae = mae(
        results_df["actual"],
        results_df[model],
    )

    model_wape = wape(
        results_df["actual"],
        results_df[model],
    )

    mean_mase = (
        scores_df[
            scores_df["model"] == model
        ]["MASE"]
        .mean()
    )

    overall_scores.append(
        {
            "model": model,
            "MAE": model_mae,
            "WAPE": model_wape,
            "MASE": mean_mase,
        }
    )


overall_scores_df = pd.DataFrame(
    overall_scores
)


print("\n" + "=" * 110)
print(
    "OVERALL MODEL PERFORMANCE"
)
print("=" * 110)

print(
    overall_scores_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# BEST MODEL OVERALL
# ============================================================

best_mae = overall_scores_df.loc[
    overall_scores_df["MAE"].idxmin()
]

best_mase = overall_scores_df.loc[
    overall_scores_df["MASE"].idxmin()
]


print("\n" + "=" * 110)
print(
    "BEST EXISTING MODELS"
)
print("=" * 110)

print(
    f"Best by MAE : "
    f"{best_mae['model']} "
    f"({best_mae['MAE']:.4f})"
)

print(
    f"Best by MASE: "
    f"{best_mase['model']} "
    f"({best_mase['MASE']:.4f})"
)


# ============================================================
# BEST MODEL PER PRODUCT
# ============================================================

best_by_product = (
    scores_df
    .sort_values(
        ["product_id", "MASE"],
        na_position="last",
    )
    .groupby(
        "product_id",
        as_index=False,
    )
    .first()
)


print("\n" + "=" * 110)
print(
    "BEST MODEL FOR EACH PRODUCT"
)
print("=" * 110)

print(
    best_by_product[
        [
            "product_id",
            "product_name",
            "model",
            "MAE",
            "WAPE",
            "MASE",
        ]
    ].to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)


# ============================================================
# SAVE
# ============================================================

results_df.to_csv(
    "all_products_backtest_predictions.csv",
    index=False,
)

scores_df.to_csv(
    "all_products_product_model_scores.csv",
    index=False,
)

overall_scores_df.to_csv(
    "all_products_overall_model_scores.csv",
    index=False,
)

best_by_product.to_csv(
    "best_model_per_product.csv",
    index=False,
)


print("\n" + "=" * 110)
print("FILES SAVED")
print("=" * 110)

print(
    "all_products_backtest_predictions.csv"
)

print(
    "all_products_product_model_scores.csv"
)

print(
    "all_products_overall_model_scores.csv"
)

print(
    "best_model_per_product.csv"
)