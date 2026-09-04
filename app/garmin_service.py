"""
garmin_service.py
─────────────────
Thin wrapper around python-garminconnect / garth.
Handles:
  - Phase 1: upload body-composition .fit files (weight, muscle mass, etc.)
  - Phase 2: create structured workouts via Garmin API and schedule them
"""

import os
import json
import logging
from datetime import datetime, date
from pathlib import Path

import garth
from garminconnect import Garmin

logger = logging.getLogger(__name__)

TOKEN_DIR = os.environ.get('GARTH_HOME', './out/data/garmin_tokens')


# ──────────────────────────────────────────────
#  Auth helpers
# ──────────────────────────────────────────────

def get_client() -> Garmin:
    """Return an authenticated Garmin client using the existing Garth tokens."""
    Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)

    try:
        # Restore the existing Garth OAuth session.
        garth.resume(TOKEN_DIR)

        # Create the GarminConnect wrapper without calling login().
        client = Garmin()

        # Reuse the already-authenticated Garth HTTP client.
        client.client = garth.client

        # Verify that the restored session actually works.
        client.client.connectapi("/userprofile-service/socialProfile")

        logger.info("Garmin: reused existing Garth tokens from %s", TOKEN_DIR)

        return client

    except Exception as exc:
        logger.warning(
            "Garmin: could not restore saved Garth session: %s",
            exc,
        )
        raise RuntimeError(
            "No valid Garmin session. Open /auth in the web app to log in."
        ) from exc


def login_with_credentials(email: str, password: str, mfa_code: str | None = None) -> bool:
    """
    Do a full SSO login, save tokens to TOKEN_DIR.
    Called once from the setup page or when tokens expire.
    """
    Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)
    client = Garmin(email=email, password=password)
    try:
        client.login()
    except Exception as exc:
        # Garmin may ask for MFA; the garminconnect library raises a specific error
        if mfa_code and "MFA" in str(type(exc).__name__).upper():
            client.login(mfa_code=mfa_code)
        else:
            raise
    client.garth.dump(TOKEN_DIR)
    logger.info("Garmin: login successful, tokens saved.")
    return True


# ──────────────────────────────────────────────
#  Phase 1 – Body composition / weight
# ──────────────────────────────────────────────

def upload_body_metrics(fit_file_path: str) -> dict:
    """
    Upload a .fit file (body composition / weight) to Garmin Connect.
    Garmin expects multipart/form-data with the raw bytes, not a file path.
    """
    client = get_client()
    with open(fit_file_path, 'rb') as f:
        fit_bytes = f.read()

    url = "/upload-service/upload"
    files = {
        "file": ("body_composition.fit", fit_bytes, "application/octet-stream"),
    }
    result = client.garth.post("connectapi", url, files=files, api=True).json()
    logger.info("Garmin body upload result: %s", result)
    return result


def upload_weight_directly(weight_kg: float, measured_at: datetime | None = None) -> dict:
    """
    Alternative: push weight using the Garmin Connect weight endpoint
    (no .fit file needed). Useful as a fallback.
    """
    client = get_client()
    ts = measured_at or datetime.utcnow()
    result = client.set_body_composition(
        timestamp=ts,
        weight=weight_kg,
    )
    return result


# ──────────────────────────────────────────────
#  Phase 2 – Structured workouts
# ──────────────────────────────────────────────

# Map from our JSON sport_type strings to garminconnect sport type keys
SPORT_TYPE_MAP = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running"},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "swimming": {"sportTypeId": 5, "sportTypeKey": "lap_swimming"},
    "strength": {"sportTypeId": 4, "sportTypeKey": "strength_training"},
    "walking": {"sportTypeId": 9, "sportTypeKey": "walking"},
    "hiking": {"sportTypeId": 3, "sportTypeKey": "hiking"},
    "cardio": {"sportTypeId": 26, "sportTypeKey": "fitness_equipment"},
}


def build_workout_payload(workout_json: dict) -> dict:
    """
    Convert our internal workout JSON format to the Garmin Connect
    workout API payload format.

    Expected workout_json structure:
    {
      "name": "Easy Run 5K",
      "sport_type": "running",
      "scheduled_date": "2026-03-25",
      "duration_secs": 1800,
      "steps": [
        {"type": "warmup",   "duration_secs": 300,  "intensity": "warmup"},
        {"type": "interval", "duration_secs": 1200, "target_pace_min_per_km": 5.5},
        {"type": "cooldown", "duration_secs": 300,  "intensity": "cooldown"}
      ]
    }
    """
    sport_key = workout_json.get("sport_type", "running").lower()
    sport_type = SPORT_TYPE_MAP.get(sport_key, SPORT_TYPE_MAP["running"])

    steps = []
    for i, step in enumerate(workout_json.get("steps", []), start=1):
        step_type = step.get("type", "interval").lower()
        duration = step.get("duration_secs", 600)
        intensity = step.get("intensity", _default_intensity(step_type))

        garmin_step = {
            "stepOrder": i,
            "stepType": {"stepTypeId": _step_type_id(step_type), "stepTypeKey": step_type},
            "durationType": {"durationTypeId": 1, "durationTypeKey": "TIME"},
            "durationValue": duration,
            "durationValueType": {"unitKey": "second"},
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
            "intensity": intensity,
            "childStepId": None,
        }

        # Pace target
        if "target_pace_min_per_km" in step:
            mps = 1000 / (step["target_pace_min_per_km"] * 60)
            garmin_step["targetType"] = {
                "workoutTargetTypeId": 6,
                "workoutTargetTypeKey": "pace.zone",
            }
            garmin_step["targetValueOne"] = round(mps * 0.9, 4)
            garmin_step["targetValueTwo"] = round(mps * 1.1, 4)

        # Heart rate target
        if "target_hr_bpm" in step:
            garmin_step["targetType"] = {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
            }
            hr = step["target_hr_bpm"]
            garmin_step["targetValueOne"] = hr - 5
            garmin_step["targetValueTwo"] = hr + 5

        # Repeat group (intervals)
        if step_type == "repeat":
            reps = step.get("repetitions", 1)
            child_steps = step.get("steps", [])
            garmin_step["numberOfIterations"] = reps
            garmin_step["childSteps"] = [
                build_workout_payload({"sport_type": sport_key, "steps": [cs]})["workoutSegments"][0]["workoutSteps"][0]
                for cs in child_steps
            ]

        steps.append(garmin_step)

    return {
        "workoutName": workout_json.get("name", "Untitled Workout"),
        "description": workout_json.get("description", ""),
        "sportType": sport_type,
        "estimatedDurationInSecs": workout_json.get("duration_secs", sum(
            s.get("duration_secs", 0) for s in workout_json.get("steps", [])
        )),
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": sport_type,
                "workoutSteps": steps,
            }
        ],
    }


def _step_type_id(step_type: str) -> int:
    mapping = {
        "warmup": 1, "cooldown": 2, "interval": 3,
        "active": 3, "rest": 4, "recovery": 4, "repeat": 6,
    }
    return mapping.get(step_type, 3)


def _default_intensity(step_type: str) -> str:
    mapping = {
        "warmup": "WARMUP", "cooldown": "COOLDOWN",
        "rest": "REST", "recovery": "RECOVERY",
    }
    return mapping.get(step_type, "ACTIVE")


def upload_and_schedule_workout(workout_json: dict) -> dict:
    """
    Upload a structured workout to Garmin Connect and schedule it on the calendar.
    Returns: {"workout_id": str, "scheduled": bool}
    """
    client = get_client()
    payload = build_workout_payload(workout_json)

    # Upload workout definition
    result = client.add_workout(payload)
    workout_id = result.get("workoutId") or result.get("workout", {}).get("workoutId")
    if not workout_id:
        raise ValueError(f"Garmin did not return a workoutId. Response: {result}")

    logger.info("Workout uploaded, ID=%s", workout_id)

    # Schedule it
    sched_date = workout_json.get("scheduled_date")
    if sched_date:
        if isinstance(sched_date, (date, datetime)):
            sched_date = sched_date.isoformat()[:10]
        client.schedule_workout(workout_id, sched_date)
        logger.info("Workout %s scheduled for %s", workout_id, sched_date)

    return {"workout_id": str(workout_id), "scheduled": bool(sched_date)}


def upload_plan(workouts: list[dict]) -> list[dict]:
    """
    Upload an entire weekly plan (list of workouts).
    Returns list of results.
    """
    results = []
    for w in workouts:
        try:
            res = upload_and_schedule_workout(w)
            res["name"] = w.get("name")
            res["status"] = "success"
        except Exception as exc:
            logger.error("Failed to upload workout %s: %s", w.get("name"), exc)
            res = {"name": w.get("name"), "status": "error", "error": str(exc)}
        results.append(res)
    return results
