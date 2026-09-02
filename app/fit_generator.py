"""
fit_generator.py
────────────────
Genera archivos .fit de composición corporal para Garmin.
Basado en el script original del usuario.
"""

import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.weight_scale_message import WeightScaleMessage
from fit_tool.profile.profile_type import Manufacturer, FileType

OUTPUT_DIR = os.environ.get('FIT_OUTPUT_FOLDER', './out/data/fit_files/body')


def generate_body_composition_fit(
    weight_kg: float,
    measured_date: date,
    body_fat_pct: Optional[float] = None,
    muscle_mass_pct: Optional[float] = None,
    visceral_fat: Optional[int] = None,
    metabolic_age: Optional[int] = None,
    metabolic_rate: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    Genera un .fit de composición corporal y devuelve la ruta del archivo.

    Campos:
      weight_kg       — peso en kg
      body_fat_pct    — % grasa corporal  (ej: 18.5)
      muscle_mass_pct — % masa muscular   (ej: 45.0) → se convierte a kg internamente
      visceral_fat    — nivel grasa visceral (1-20)
      metabolic_age   — edad metabólica en años
    """
    out_dir = Path(output_dir or OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"body_{measured_date.isoformat()}.fit"
    filepath = out_dir / filename

    # Timestamp en milisegundos (igual que el script original)
    dt = datetime.combine(measured_date, datetime.min.time())
    created = round(dt.timestamp() * 1000)

    # ── File ID ──────────────────────────────────────
    file_id_message = FileIdMessage()
    file_id_message.type = FileType.WEIGHT
    file_id_message.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id_message.product = 0
    file_id_message.time_created = created
    file_id_message.serial_number = 0x12345678

    # ── Weight Scale ─────────────────────────────────
    weight_message = WeightScaleMessage()
    weight_message.timestamp = created
    weight_message.weight = weight_kg

    if body_fat_pct is not None:
        weight_message.percent_fat = body_fat_pct

    if muscle_mass_pct is not None:
        # Garmin espera masa muscular en kg, calculamos desde el porcentaje
        weight_message.muscle_mass = weight_kg * muscle_mass_pct / 100

    if visceral_fat is not None:
        weight_message.visceral_fat_rating = visceral_fat

    if metabolic_age is not None:
        weight_message.metabolic_age = metabolic_age
    if metabolic_rate is not None:
        weight_message.active_met = metabolic_rate

    # ── Build ─────────────────────────────────────────
    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    builder.add(file_id_message)
    builder.add(weight_message)
    fit_file = builder.build()
    fit_file.to_file(str(filepath))

    return str(filepath)
