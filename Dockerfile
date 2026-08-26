# Multi-stage: builds the dashboard (frontend/) as static assets, then
# copies them into the same image as the backend so ONE Cloud Run
# service serves both the API and the dashboard, same-origin -- no
# separate Cloud Storage bucket, no CORS configuration needed for the
# dashboard's own calls. Deploy either way: this Dockerfile always
# builds fullstack; deploy/deploy_frontend.sh (a separate GCS-hosted
# dashboard) still works too if you want the dashboard decoupled from
# the backend's deploy cadence.
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
# main.py mounts this directory at "/" with html=True if it's present,
# so the dashboard build above becomes the app's root route -- see its
# comment for why this needs no SPA-fallback route (HashRouter).
COPY --from=frontend-build /app/frontend/dist ./static

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Cloud Run injects PORT; default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn bulwark.main:app --host 0.0.0.0 --port ${PORT}"]
