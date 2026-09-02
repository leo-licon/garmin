from datetime import datetime
from . import db


class BodyMetric(db.Model):
    """Daily body composition entry (Phase 1)"""
    __tablename__ = 'body_metrics'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    weight_kg = db.Column(db.Float, nullable=False)
    body_fat_pct = db.Column(db.Float)       # % grasa corporal
    muscle_mass_pct = db.Column(db.Float)    # % masa muscular
    visceral_fat = db.Column(db.Integer)     # grasa visceral (1-20)
    metabolic_age = db.Column(db.Integer)    # edad metabólica (años)
    metabolic_rate = db.Column(db.Integer)
    fit_file_path = db.Column(db.String(512))
    garmin_upload_status = db.Column(db.String(32), default='pending')
    garmin_upload_at = db.Column(db.DateTime)
    garmin_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'weight_kg': self.weight_kg,
            'body_fat_pct': self.body_fat_pct,
            'muscle_mass_pct': self.muscle_mass_pct,
            'visceral_fat': self.visceral_fat,
            'metabolic_age': self.metabolic_age,
            'metabolic_rate': self.metabolic_rate,
            'garmin_upload_status': self.garmin_upload_status,
            'garmin_upload_at': self.garmin_upload_at.isoformat() if self.garmin_upload_at else None,
            'garmin_error': self.garmin_error,
        }


class WorkoutPlan(db.Model):
    __tablename__ = 'workout_plans'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    source = db.Column(db.String(32), default='upload')
    raw_json = db.Column(db.Text, nullable=False)
    total_workouts = db.Column(db.Integer, default=0)
    processed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    workouts = db.relationship('Workout', backref='plan', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'source': self.source,
            'total_workouts': self.total_workouts,
            'workouts': [w.to_dict() for w in self.workouts],
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'created_at': self.created_at.isoformat(),
        }


class Workout(db.Model):
    __tablename__ = 'workouts'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('workout_plans.id'), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    sport_type = db.Column(db.String(64), default='running')
    scheduled_date = db.Column(db.Date, nullable=False)
    duration_secs = db.Column(db.Integer)
    description = db.Column(db.Text)
    raw_steps = db.Column(db.Text)
    fit_file_path = db.Column(db.String(512))
    garmin_workout_id = db.Column(db.String(128))
    garmin_upload_status = db.Column(db.String(32), default='pending')
    garmin_scheduled_at = db.Column(db.DateTime)
    garmin_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'name': self.name,
            'sport_type': self.sport_type,
            'scheduled_date': self.scheduled_date.isoformat(),
            'duration_secs': self.duration_secs,
            'garmin_workout_id': self.garmin_workout_id,
            'garmin_upload_status': self.garmin_upload_status,
            'garmin_scheduled_at': self.garmin_scheduled_at.isoformat() if self.garmin_scheduled_at else None,
            'garmin_error': self.garmin_error,
        }


class GarminSession(db.Model):
    __tablename__ = 'garmin_session'

    id = db.Column(db.Integer, primary_key=True, default=1)
    token_dir = db.Column(db.String(512), default='./out/data/garmin_tokens')
    is_authenticated = db.Column(db.Boolean, default=False)
    authenticated_at = db.Column(db.DateTime)
    last_used_at = db.Column(db.DateTime)
    username = db.Column(db.String(256))
