# The app as an image.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY groundbook ./groundbook
COPY seed ./seed

ENV HOST=0.0.0.0 \
    PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn groundbook.app:app --host \"$HOST\" --port \"$PORT\""]