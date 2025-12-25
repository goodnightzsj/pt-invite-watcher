FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pt_invite_watcher /app/pt_invite_watcher
COPY config /app/config
COPY README.md /app/README.md
COPY Plan.md /app/Plan.md

EXPOSE 8080

CMD ["python", "-m", "pt_invite_watcher", "run", "--host", "0.0.0.0", "--port", "8080"]

