"""
routes.py + api.py combined
────────────────────────────
Web routes (HTML pages) and REST API endpoints.
"""

import os
import json
import logging
from datetime import date, datetime
from pathlib import Path

from flask import (
    Blueprint, render_template, request, jsonify,
    redirect, url_for, flash, send_from_directory, current_app,
)
from werkzeug.utils import secure_filename

from . import db
from .models import BodyMetric, WorkoutPlan, Workout, GarminSession
from .fit_generator import generate_body_composition_fit
from .garmin_service import (
    login_with_credentials, upload_body_metrics, upload_and_schedule_workout,
)

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

ALLOWED_EXTENSIONS = {'json'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────────
#  HTML PAGES
# ──────────────────────────────────────────────

@main_bp.route('/')
def index():
    recent_metrics = BodyMetric.query.order_by(BodyMetric.date.desc()).limit(7).all()
    last_metric = recent_metrics[0] if recent_metrics else None
    recent_plans = WorkoutPlan.query.order_by(WorkoutPlan.created_at.desc()).limit(5).all()
    garmin_ok = _garmin_is_authenticated()
    return render_template(
        'index.html',
        recent_metrics=recent_metrics,
        last_metric=last_metric,
        recent_plans=recent_plans,
        garmin_ok=garmin_ok,
    )


@main_bp.route('/body-metrics')
def body_metrics():
    metrics = BodyMetric.query.order_by(BodyMetric.date.desc()).all()
    return render_template('body_metrics.html', metrics=metrics, garmin_ok=_garmin_is_authenticated())


@main_bp.route('/workouts')
def workouts():
    plans = WorkoutPlan.query.order_by(WorkoutPlan.created_at.desc()).all()
    watch_dir = os.environ.get('WORKOUT_WATCH_DIR', './out/data/workouts/inbox')
    return render_template('workouts.html', plans=plans, watch_dir=watch_dir)


@main_bp.route('/auth', methods=['GET', 'POST'])
def auth():
    """Setup page: enter Garmin credentials once."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        mfa = request.form.get('mfa_code') or None
        try:
            login_with_credentials(email, password, mfa)
            session = GarminSession.query.first() or GarminSession()
            session.is_authenticated = True
            session.authenticated_at = datetime.utcnow()
            session.username = email
            db.session.add(session)
            db.session.commit()
            flash('✅ Conectado a Garmin correctamente.', 'success')
            return redirect(url_for('main.index'))
        except Exception as exc:
            flash(f'❌ Error al conectar: {exc}', 'error')
    return render_template('auth.html', garmin_ok=_garmin_is_authenticated())


# ──────────────────────────────────────────────
#  REST API – Body Metrics (Phase 1)
# ──────────────────────────────────────────────

@api_bp.route('/body-metrics', methods=['GET'])
def list_body_metrics():
    metrics = BodyMetric.query.order_by(BodyMetric.date.desc()).limit(30).all()
    return jsonify([m.to_dict() for m in metrics])


@api_bp.route('/body-metrics', methods=['POST'])
def create_body_metric():
    """
    POST /api/body-metrics
    {
      "date": "2026-03-18",
      "weight_kg": 82.5,
      "muscle_mass_kg": 38.2,
      "body_fat_pct": 18.5,
      "bone_mass_kg": 3.2,
      "water_pct": 55.0,
      "bmi": 24.1,
      "visceral_fat": 8
    }
    """
    data = request.get_json(force=True)
    measured_date = date.fromisoformat(data['date'])
    existing = BodyMetric.query.filter_by(date=measured_date).first()
    if existing:
        return jsonify({'error': 'Entry for this date already exists'}), 409

    metric = BodyMetric(
        date=measured_date,
        weight_kg=data['weight_kg'],
        body_fat_pct=data.get('body_fat_pct'),
        muscle_mass_pct=data.get('muscle_mass_pct'),
        visceral_fat=data.get('visceral_fat'),
        metabolic_age=data.get('metabolic_age'),
        metabolic_rate=data.get('metabolic_rate'),
    )
    db.session.add(metric)
    db.session.flush()
    # Generate .fit file
    try:
        fit_path = generate_body_composition_fit(
            weight_kg=metric.weight_kg,
            measured_date=measured_date,
            body_fat_pct=metric.body_fat_pct,
            muscle_mass_pct=metric.muscle_mass_pct,
            visceral_fat=metric.visceral_fat,
            metabolic_age=metric.metabolic_age,
            metabolic_rate=metric.metabolic_rate,
        )
        metric.fit_file_path = fit_path
    except Exception as exc:
        logger.error("FIT generation failed: %s", exc)
        db.session.commit()
        return jsonify({'error': f'FIT generation failed: {exc}', 'metric': metric.to_dict()}), 500

    # Upload to Garmin
    try:
        upload_body_metrics(fit_path)
        metric.garmin_upload_status = 'success'
        metric.garmin_upload_at = datetime.utcnow()
    except Exception as exc:
        metric.garmin_upload_status = 'error'
        metric.garmin_error = str(exc)
        logger.error("Garmin upload failed: %s", exc)

    db.session.commit()
    return jsonify(metric.to_dict()), 201


@api_bp.route('/body-metrics/<int:metric_id>/retry-upload', methods=['POST'])
def retry_body_upload(metric_id):
    metric = BodyMetric.query.get_or_404(metric_id)
    if not metric.fit_file_path or not Path(metric.fit_file_path).exists():
        return jsonify({'error': 'FIT file not found, regenerate first'}), 400
    try:
        upload_body_metrics(metric.fit_file_path)
        metric.garmin_upload_status = 'success'
        metric.garmin_upload_at = datetime.utcnow()
        metric.garmin_error = None
    except Exception as exc:
        metric.garmin_upload_status = 'error'
        metric.garmin_error = str(exc)
    db.session.commit()
    return jsonify(metric.to_dict())


# ──────────────────────────────────────────────
#  REST API – Workout Plans (Phase 2)
# ──────────────────────────────────────────────

@api_bp.route('/workout-plans', methods=['GET'])
def list_plans():
    plans = WorkoutPlan.query.order_by(WorkoutPlan.created_at.desc()).all()
    return jsonify([p.to_dict() for p in plans])


@api_bp.route('/workout-plans/upload', methods=['POST'])
def upload_plan():
    """Upload a JSON file with one or more workouts."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only .json files accepted'}), 400

    filename = secure_filename(file.filename)
    raw = file.read().decode('utf-8')

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return jsonify({'error': f'Invalid JSON: {exc}'}), 400

    workouts_data = data if isinstance(data, list) else data.get('workouts', [data])

    plan = WorkoutPlan(
        filename=filename,
        source='upload',
        raw_json=raw,
        total_workouts=len(workouts_data),
        processed_at=datetime.utcnow(),
    )
    db.session.add(plan)
    db.session.flush()

    results = []
    for w_data in workouts_data:
        sched_str = w_data.get('scheduled_date') or w_data.get('date')
        sched_date = date.fromisoformat(sched_str) if sched_str else date.today()

        workout = Workout(
            plan_id=plan.id,
            name=w_data.get('name', 'Unnamed'),
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
            results.append({'name': workout.name, 'status': 'success', 'garmin_id': result['workout_id']})
        except Exception as exc:
            workout.garmin_upload_status = 'error'
            workout.garmin_error = str(exc)
            results.append({'name': workout.name, 'status': 'error', 'error': str(exc)})

    db.session.commit()
    return jsonify({'plan_id': plan.id, 'results': results}), 201


@api_bp.route('/workout-plans/<int:plan_id>', methods=['GET'])
def get_plan(plan_id):
    plan = WorkoutPlan.query.get_or_404(plan_id)
    return jsonify(plan.to_dict())


@api_bp.route('/workouts/<int:workout_id>/retry', methods=['POST'])
def retry_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    raw = json.loads(workout.raw_steps)
    w_data = {
        'name': workout.name,
        'sport_type': workout.sport_type,
        'scheduled_date': workout.scheduled_date.isoformat(),
        'duration_secs': workout.duration_secs,
        'description': workout.description,
        'steps': raw,
    }
    try:
        result = upload_and_schedule_workout(w_data)
        workout.garmin_workout_id = result['workout_id']
        workout.garmin_upload_status = 'scheduled'
        workout.garmin_scheduled_at = datetime.utcnow()
        workout.garmin_error = None
    except Exception as exc:
        workout.garmin_upload_status = 'error'
        workout.garmin_error = str(exc)
    db.session.commit()
    return jsonify(workout.to_dict())


# ──────────────────────────────────────────────
#  Garmin auth status
# ──────────────────────────────────────────────

@api_bp.route('/garmin/status', methods=['GET'])
def garmin_status():
    return jsonify({
        'authenticated': _garmin_is_authenticated(),
        'token_dir': os.environ.get('GARTH_HOME', './out/data/garmin_tokens'),
    })


def _garmin_is_authenticated() -> bool:
    token_dir = Path(os.environ.get('GARTH_HOME', './out/data/garmin_tokens'))
    return token_dir.exists() and any(token_dir.iterdir())
