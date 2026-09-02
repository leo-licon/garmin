FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Make sure Python can find the app package from /app
ENV PYTHONPATH=/app

COPY . .

# Persistent data directories
RUN mkdir -p /data/garmin_tokens \
             /data/fit_files/body \
             /data/workouts/inbox \
             /data/workouts/processed \
             /data/workouts/error

VOLUME ["/data"]

ENV FLASK_APP=run.py
ENV FLASK_ENV=production
ENV GARTH_HOME=/data/garmin_tokens
ENV FIT_OUTPUT_FOLDER=/data/fit_files/body
ENV WORKOUT_WATCH_DIR=/data/workouts/inbox
ENV WORKOUT_PROCESSED_DIR=/data/workouts/processed
ENV WORKOUT_ERROR_DIR=/data/workouts/error
ENV DATABASE_URL=sqlite:////data/garmin_sync.db

EXPOSE 5000

CMD ["gunicorn", "--worker-class", "gevent", "-w", "1", "--bind", "0.0.0.0:5000", "run:app"]
