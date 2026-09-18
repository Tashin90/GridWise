# GridWise FastAPI service
FROM python:3.12-slim

# Avoid writing .pyc files and enable unbuffered logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the application code.
COPY backend ./backend

# Deployment-provided port (defaults to 8000).
ENV PORT=8000
EXPOSE 8000

# Listen on 0.0.0.0 so the container is reachable from outside.
# Uses `python -m uvicorn` so it does not depend on the Scripts dir being on PATH,
# and binds to the deployment-provided PORT (Railway sets this automatically).
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
