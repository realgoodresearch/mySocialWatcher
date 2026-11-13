FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY docker/api_v2/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY mysocialwatcher /app/mysocialwatcher

EXPOSE 8001
CMD ["sh", "-c", "exec uvicorn mysocialwatcher.api_v2.main:app --host 0.0.0.0 --port 8001 --workers ${SOCIALWATCHER_V2_WORKERS:-1}"]
