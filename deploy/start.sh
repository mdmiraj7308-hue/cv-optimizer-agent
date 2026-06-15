#!/bin/bash
set -euo pipefail

PORT="${PORT:-10000}"

echo "Starting Job Finder (single-container mode on port ${PORT})..."

# Generate nginx config (sed avoids clobbering nginx $variables)
sed "s/PORT_PLACEHOLDER/${PORT}/g" /app/deploy/nginx.conf.template \
    > /etc/nginx/conf.d/app.conf

rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# FastAPI backend (internal)
uvicorn backend:fastapi_app --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!

# Streamlit frontend (internal)
streamlit run app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

# Wait until both services respond
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1 \
       && curl -sf http://127.0.0.1:8501/ > /dev/null 2>&1; then
        echo "FastAPI and Streamlit are ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Services failed to start within 30s." >&2
        kill "$UVICORN_PID" "$STREAMLIT_PID" 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# nginx in foreground (keeps container alive)
exec nginx -g 'daemon off;'
