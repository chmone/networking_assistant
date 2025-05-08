#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Define default ports if not set via environment variables
FASTAPI_PORT=${PORT_FASTAPI:-8000}
STREAMLIT_PORT=${PORT_STREAMLIT:-8501}

echo "Starting FastAPI backend on port $FASTAPI_PORT..."
# Run Uvicorn in the background
# Use 0.0.0.0 to bind to all interfaces within the container
# Ensure PYTHONPATH allows imports if needed, though src should be importable from /app
uvicorn src.web_app.api_main:app --host 0.0.0.0 --port $FASTAPI_PORT --workers ${UVICORN_WORKERS:-1} &

# Wait a few seconds for the backend to potentially start (optional)
sleep 5 

echo "Starting Streamlit frontend on port $STREAMLIT_PORT..."
# Run Streamlit in the foreground (this will keep the container running)
# The --server.address=0.0.0.0 makes it accessible outside the container
streamlit run src/web_app/app.py --server.port $STREAMLIT_PORT --server.address 0.0.0.0 --server.enableCORS false --server.enableXsrfProtection false

# Note: This runs Streamlit in the foreground. If Streamlit exits, the container stops.
# More robust solutions might use a process manager like supervisord inside the container. 