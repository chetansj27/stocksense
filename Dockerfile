FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
# Cloud Run: sample data is generated on first request; SQLite is ephemeral (fine for a demo).
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
