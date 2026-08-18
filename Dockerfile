FROM python:3.11-slim

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
ENV DATA_DIR=/data
ENV KLIPWAE_DB_PATH=/data/jobs.db
RUN mkdir -p /data

EXPOSE 7860
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-7860}"]