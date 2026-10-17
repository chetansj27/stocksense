"""BigQuery backend: load data and forecast with BigQuery ML ARIMA_PLUS.
Enabled when BQ_DATASET is set (plus GOOGLE_CLOUD_PROJECT / application default credentials)."""
import functools
import os

import pandas as pd

import data

MODEL = "demand_model"


def enabled() -> bool:
    return bool(os.getenv("BQ_DATASET"))


def _client():
    from google.cloud import bigquery

    return bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))


def _fq(c, name: str) -> str:
    return f"`{c.project}.{os.getenv('BQ_DATASET')}.{name}`"


def load_and_train(horizon: int = 14) -> None:
    """Copy local tables to BigQuery and (re)train one ARIMA_PLUS model across all SKUs."""
    from google.cloud import bigquery

    c = _client()
    ds = os.getenv("BQ_DATASET")
    c.create_dataset(ds, exists_ok=True)
    cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    for table in ("sales", "inventory", "products"):
        df = data.load(table)
        if table == "sales":
            df["date"] = pd.to_datetime(df["date"]).dt.date
        c.load_table_from_dataframe(df, f"{c.project}.{ds}.{table}", job_config=cfg).result()
    c.query(f"""
        CREATE OR REPLACE MODEL {_fq(c, MODEL)}
        OPTIONS(model_type='ARIMA_PLUS', time_series_timestamp_col='date',
                time_series_data_col='units', time_series_id_col='sku',
                horizon={horizon}, auto_arima=TRUE)
        AS SELECT date, sku, units FROM {_fq(c, 'sales')}
    """).result()
    forecasts.cache_clear()


@functools.lru_cache(maxsize=1)
def forecasts(horizon: int = 14) -> dict[str, pd.DataFrame]:
    c = _client()
    df = c.query(f"""
        SELECT sku, DATE(forecast_timestamp) AS date, GREATEST(forecast_value, 0) AS forecast
        FROM ML.FORECAST(MODEL {_fq(c, MODEL)}, STRUCT({horizon} AS horizon, 0.9 AS confidence_level))
        ORDER BY sku, date
    """).to_dataframe()
    return {sku: g[["date", "forecast"]].reset_index(drop=True) for sku, g in df.groupby("sku")}
