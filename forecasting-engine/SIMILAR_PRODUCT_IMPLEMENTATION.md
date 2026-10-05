# Similar Product Forecasting (V1)

This change adds a simple historical-analogue path for products with too little own sales history.

## What changed

- `src/similar_products.py`
  - READ-ONLY Odoo query for explicit historical product relationships.
  - Uses `main_product` and `product_template_similar_rel`.
  - Converts template relationships to the existing `product_product.id` used by `monthly_df`.
  - Keeps only old products with at least 6 selling months.
  - Builds lifecycle-aligned old-product demand and produces a scaled analogue forecast.
  - Name-only similarity is intentionally not used for forecasting.

- `src/pipeline.py`
  - `forecast_all_products()` now accepts an optional `similar_candidates` DataFrame.
  - For insufficient-history products, it tries the historical analogue method first.
  - Existing category fallback remains as the fallback when no usable analogue exists.

- `scripts/refresh_similar_product_candidates.py`
  - Refreshes `data/historical_similar_product_candidates.csv` using SELECT-only Odoo access.
  - Never writes to PostgreSQL/Odoo.

- `scripts/backtest_similar_products.py`
  - Exploratory backtest.
  - Reads Odoo only and writes a local CSV.
  - Never writes a PostgreSQL table.

- `tests/test_similar_products.py`
  - Offline unit tests for the new module.

## Important database rule

The new similarity code is READ-ONLY. Do not run the legacy `run_all.py` during this experiment because that existing script writes forecast tables back to the database configured in `.env`.

The new refresh/backtest scripts only run SELECT queries and save local CSV files.

## Local setup

Copy the project changes into your forecasting engine directory. Keep your existing `.env`; this package intentionally does not contain it.

### 1. Verify the new code (no database access)

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests\test_similar_products.py
```

### 2. Refresh the similar-product snapshot (read-only Odoo)

```powershell
& .\.venv\Scripts\python.exe scripts\refresh_similar_product_candidates.py
```

This only runs SELECT statements and saves:

```text
data\historical_similar_product_candidates.csv
```

### 3. Run the similar-product logic on the existing 10-product POC

```powershell
& .\.venv\Scripts\python.exe scripts\run_similar_product_poc.py
```

This only reads Odoo and saves:

```text
data\similar_product_poc_forecasts.csv
```

The script does not write any PostgreSQL/Odoo table.

### 4. Run the exploratory backtest

```powershell
& .\.venv\Scripts\python.exe scripts\backtest_similar_products.py
```

The result is written to:

```text
data\similar_product_backtest.csv
```

## Important database rule

Do **not** run the legacy `run_all.py` for this experiment. That existing script writes `forecast_vs_actual` and `product_demand_forecast` tables to the database configured in `.env`. The three scripts above are the safe path for this phase.
