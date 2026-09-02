"""
watcher.py
──────────
Watches a directory for new workout JSON files and triggers the upload pipeline.
Uses watchdog library: pip install watchdog

Run as a background thread inside Flask app (via socketio.start_background_task),
or as a standalone process alongside the web app.
"""

import os
import time
import json
import logging
from pathlib import Path
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

logger = logging.getLogger(__name__)

WATCH_DIR = os.environ.get('WORKOUT_WATCH_DIR', './out/data/workouts/inbox')
PROCESSED_DIR = os.environ.get('WORKOUT_PROCESSED_DIR', './out/data/workouts/processed')
ERROR_DIR = os.environ.get('WORKOUT_ERROR_DIR', './out/data/workouts/error')


class WorkoutFileHandler(FileSystemEventHandler):
    """Processes new .json files dropped into the watch directory."""

    def __init__(self, app, socketio_instance=None):
        self.app = app
        self.socketio = socketio_instance
        Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
        Path(ERROR_DIR).mkdir(parents=True, exist_ok=True)

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != '.json':
            return
        # Small delay to ensure file is fully written
        time.sleep(0.5)
        self._process_file(path)

    def _process_file(self, path: Path):
        logger.info("Watcher: detected new file %s", path)
        with self.app.app_context():
            try:
                self._handle(path)
            except Exception as exc:
                logger.error("Watcher: error processing %s: %s", path, exc)
                self._move_to(path, ERROR_DIR)

    def _handle(self, path: Path):
        from .models import db, WorkoutPlan, Workout
        from .garmin_service import upload_and_schedule_workout

        raw = path.read_text(encoding='utf-8')
        data = json.loads(raw)

        # Normalise: support single workout dict or list of workouts
        workouts_data = data if isinstance(data, list) else data.get('workouts', [data])

        plan = WorkoutPlan(
            filename=path.name,
            source='watched_dir',
            raw_json=raw,
            total_workouts=len(workouts_data),
            processed_at=datetime.utcnow(),
        )
        db.session.add(plan)
        db.session.flush()

        results = []
        for w_data in workouts_data:
            from datetime import date as date_type
            sched_str = w_data.get('scheduled_date') or w_data.get('date')
            if isinstance(sched_str, str):
                sched_date = date_type.fromisoformat(sched_str)
            else:
                sched_date = date_type.today()

            workout = Workout(
                plan_id=plan.id,
                name=w_data.get('name', 'Unnamed Workout'),
                sport_type=w_data.get('sport_type', 'running'),
                scheduled_date=sched_date,
                duration_secs=w_data.get('duration_secs'),
                description=w_data.get('description', ''),
                raw_steps=json.dumps(w_data.get('steps', [])),
            )
            db.session.add(workout)
            db.session.flush()

            try:
                result = upload_and_schedule_workout(w_data)
                workout.garmin_workout_id = result['workout_id']
                workout.garmin_upload_status = 'scheduled' if result['scheduled'] else 'uploaded'
                workout.garmin_scheduled_at = datetime.utcnow()
                status = 'success'
            except Exception as exc:
                workout.garmin_upload_status = 'error'
                workout.garmin_error = str(exc)
                status = 'error'
                logger.error("Failed to upload workout '%s': %s", workout.name, exc)

            results.append({'name': workout.name, 'status': status})

        db.session.commit()

        # Notify frontend via WebSocket
        if self.socketio:
            self.socketio.emit('plan_processed', {
                'plan_id': plan.id,
                'filename': path.name,
                'results': results,
            })

        # Move file to processed directory
        self._move_to(path, PROCESSED_DIR)
        logger.info("Watcher: finished processing %s → %d workouts", path.name, len(workouts_data))

    @staticmethod
    def _move_to(path: Path, dest_dir: str):
        dest = Path(dest_dir) / path.name
        # Avoid overwriting
        if dest.exists():
            stem = path.stem
            suffix = path.suffix
            dest = Path(dest_dir) / f"{stem}_{int(time.time())}{suffix}"
        path.rename(dest)


def start_watcher(app, socketio_instance=None):
    """Start the directory watcher in a background thread."""
    Path(WATCH_DIR).mkdir(parents=True, exist_ok=True)
    handler = WorkoutFileHandler(app, socketio_instance)
    observer = Observer()
    observer.schedule(handler, WATCH_DIR, recursive=False)
    observer.start()
    logger.info("Directory watcher started on %s", WATCH_DIR)
    return observer
