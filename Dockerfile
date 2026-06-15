FROM python:3.12-slim

# System deps: nginx (reverse proxy) + libraries for xhtml2pdf PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/deploy/start.sh \
    && rm -f /etc/nginx/sites-enabled/default

# Render injects PORT; nginx listens on it and routes to Streamlit + FastAPI
EXPOSE 10000

CMD ["/app/deploy/start.sh"]
