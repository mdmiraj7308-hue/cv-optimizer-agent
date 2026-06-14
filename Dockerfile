FROM python:3.12-slim

# WeasyPrint requires Pango, Cairo and GDK-PixBuf for HTML-to-PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# FastAPI port
EXPOSE 8000
# Streamlit port
EXPOSE 8501

# Default: run the FastAPI + APScheduler backend.
# To run Streamlit instead, override CMD:
#   docker run ... career-advisor streamlit run app.py --server.port 8501 --server.address 0.0.0.0
CMD ["uvicorn", "app:fastapi_app", "--host", "0.0.0.0", "--port", "8000"]
