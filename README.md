# StockSense

Demand forecasting and inventory copilot: forecasts, safety-stock reorder planning, what-if
scenarios, a Gemini agent that queries data and raises purchase orders for human approval, and a
60-day backtest against a rolling-average policy.

## Features
Risk table with filters and days-of-cover bars, demand surge/drop alerts, what-if scenarios, copilot with
suggested questions and tools (SQL, plan, orders, alerts), purchase orders with product names, bulk
approve/reject, CSV export and delete-all, a customer-facing customer assistant (storefront plus Gemini chat,
link: `<app-url>/?view=customer`) that feeds unmet-demand signals back to the manager, 60-day backtest versus a rolling-average policy.

## Run locally (no GCP needed except Gemini)
```
pip install -r requirements.txt
python test_offline.py                 # offline tests
export GEMINI_API_KEY=your-key
python smoke_test.py                   # live Gemini checks
streamlit run app.py
```

## Google Cloud mode
| Env var | Effect |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Gemini via Vertex AI (no key) |
| `BQ_DATASET=stocksense` | Forecast with BigQuery ML ARIMA_PLUS; click "Train BigQuery ML model" once |
| `USE_FIRESTORE=true` | Purchase orders persist in Firestore |

## Deploy to Cloud Run
```
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com bigquery.googleapis.com firestore.googleapis.com
gcloud firestore databases create --location=us-central1      # once
gcloud run deploy stocksense --source . --region us-central1 --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=PROJECT,GOOGLE_CLOUD_LOCATION=us-central1,BQ_DATASET=stocksense,USE_FIRESTORE=true
```
Grant the Cloud Run service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`):
`roles/aiplatform.user`, `roles/bigquery.dataEditor`, `roles/bigquery.jobUser`, `roles/datastore.user`.

If BigQuery or Firestore is unavailable, set neither env var and the app runs fully on local fallbacks.
See `DEMO.md` for the presentation script.

**Note:** the `?view=customer` link hides the manager UI but is not authentication. Put the app behind IAP/auth before real use.
