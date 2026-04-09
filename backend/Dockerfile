FROM python:3.11-slim

# System deps: ffmpeg (render), libGL (scenedetect/cv2), curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security
RUN addgroup --gid 1001 appgroup && \
    adduser --uid 1001 --gid 1001 --disabled-password --gecos "" appuser && \
    chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# Default: API server. Override with `command:` in docker-compose for workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
