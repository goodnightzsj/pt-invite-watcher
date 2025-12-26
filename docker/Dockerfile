FROM node:18-slim AS webui

WORKDIR /app

COPY webui/package.json /app/webui/package.json
COPY webui/package-lock.json /app/webui/package-lock.json
RUN npm --prefix /app/webui ci

COPY webui /app/webui
RUN npm --prefix /app/webui run build


FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pt_invite_watcher /app/pt_invite_watcher
COPY --from=webui /app/pt_invite_watcher/webui_dist /app/pt_invite_watcher/webui_dist
COPY config /app/config
COPY README.md /app/README.md

EXPOSE 8080

CMD ["python", "-m", "pt_invite_watcher", "run", "--host", "0.0.0.0", "--port", "8080"]
