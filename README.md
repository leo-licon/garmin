# ⌚ Garmin Sync Hub

Sistema completo para sincronizar automáticamente composición corporal y entrenamientos estructurados con Garmin Connect, desde una interfaz web en contenedor Docker.

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    GARMIN SYNC HUB                          │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Flask Web   │    │  Watcher     │    │  Garmin      │  │
│  │  Dashboard   │    │  (watchdog)  │    │  Service     │  │
│  │              │    │              │    │  (garth)     │  │
│  │ /            │    │ /data/       │    │              │  │
│  │ /body-metrics│    │ workouts/    │◄───│ OAuth tokens │  │
│  │ /workouts    │    │ inbox/       │    │ persist in   │  │
│  │ /auth        │    │              │    │ /data/       │  │
│  └──────┬───────┘    └──────┬───────┘    │ garmin_      │  │
│         │                  │            │ tokens/      │  │
│         │    SocketIO       │            └──────────────┘  │
│         ▼    (WebSocket)   ▼                               │
│  ┌──────────────────────────────────────┐                  │
│  │              SQLite DB               │                  │
│  │  body_metrics | workout_plans        │                  │
│  │  workouts     | garmin_session       │                  │
│  └──────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ HTTPS
┌─────────────────────┐
│  Garmin Connect API │
│  (via garth OAuth)  │
│                     │
│  • Upload weight    │
│  • Add workout      │
│  • Schedule workout │
└─────────────────────┘
         │
         ▼ sync
    ⌚ Tu reloj Garmin
```

---

## Fase 1 — Composición corporal

### Flujo
1. Abres el dashboard en `http://localhost:5000`
2. Llenas los campos: peso, masa muscular, grasa, etc.
3. Haces click en **"Generar .fit y subir a Garmin"**
4. El sistema:
   - Genera el `.fit` usando el Garmin FIT SDK
   - Lo sube vía `garminconnect` a Garmin Connect
   - Guarda el estado en la BD
5. Tu reloj lo ve al siguiente sync

### Formato JSON alternativo (para scripts externos)
```json
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
```

---

## Fase 2 — Plan de entrenamientos

### Opción A: Subir desde la interfaz web
Arrastra tu `workouts.json` en el dashboard → el sistema procesa y agenda automáticamente.

### Opción B: Directorio vigilado (automático)
```bash
# Copia tu JSON en el directorio inbox
cp mi-plan-semana-12.json ./my-workouts/
# (si mapeaste el volumen en docker-compose.yml)
```
El watcher lo detecta en segundos y:
1. Parsea el JSON
2. Sube cada workout a Garmin Connect
3. Lo agenda en el calendario Garmin para la fecha indicada
4. Notifica en tiempo real vía WebSocket al dashboard

### Formato esperado del JSON de entrenamientos
```json
[
  {
    "name": "Carrera Fácil 5K",
    "sport_type": "running",
    "scheduled_date": "2026-03-25",
    "duration_secs": 1800,
    "description": "Rodaje suave de recuperación",
    "steps": [
      {"type": "warmup",   "duration_secs": 300},
      {"type": "interval", "duration_secs": 1200, "target_pace_min_per_km": 6.0},
      {"type": "cooldown", "duration_secs": 300}
    ]
  },
  {
    "name": "Intervalos 4x800m",
    "sport_type": "running",
    "scheduled_date": "2026-03-27",
    "steps": [
      {"type": "warmup", "duration_secs": 600},
      {
        "type": "repeat",
        "repetitions": 4,
        "steps": [
          {"type": "interval", "duration_secs": 200, "target_pace_min_per_km": 4.0},
          {"type": "recovery", "duration_secs": 90}
        ]
      },
      {"type": "cooldown", "duration_secs": 600}
    ]
  }
]
```

### Tipos de deporte soportados
| `sport_type` | Descripción |
|---|---|
| `running` | Carrera |
| `cycling` | Ciclismo |
| `swimming` | Natación |
| `strength` | Fuerza/gym |
| `walking` | Caminata |
| `hiking` | Senderismo |
| `cardio` | Cardio general |

### Tipos de paso soportados
| `type` | Intensidad por defecto | Notas |
|---|---|---|
| `warmup` | WARMUP | Calentamiento |
| `interval` | ACTIVE | Intervalo activo |
| `recovery` | RECOVERY | Recuperación activa |
| `rest` | REST | Descanso completo |
| `cooldown` | COOLDOWN | Enfriamiento |
| `repeat` | — | Grupo repetido, requiere `repetitions` y `steps` |

### Targets disponibles por paso
```json
{"target_pace_min_per_km": 5.5}    // Ritmo en min/km
{"target_hr_bpm": 145}              // Frecuencia cardíaca
// (sin target = "no.target")
```

---

## Instalación

### 1. Requisitos
- Docker + Docker Compose

### 2. Arrancar el sistema
```bash
git clone <este-repo>
cd garmin-sync-system
docker compose up -d
```

### 3. Conectar Garmin (una sola vez)
Abre `http://localhost:5000/auth` → ingresa tu email y contraseña de Garmin Connect.

Si tienes MFA activado, el campo MFA aparece si es necesario.

Los tokens OAuth se guardan en el volumen persistente y se reusan automáticamente. **Solo necesitas hacer login una vez.**

### 4. Usar
- Dashboard: `http://localhost:5000`
- Registrar métricas: formulario en el dashboard
- Subir plan: arrastrar JSON en el dashboard
- API REST: ver endpoints abajo

---

## API REST completa

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/api/body-metrics` | Lista las últimas 30 métricas |
| POST | `/api/body-metrics` | Crear métrica → genera FIT → sube |
| POST | `/api/body-metrics/{id}/retry-upload` | Reintentar subida a Garmin |
| GET | `/api/workout-plans` | Lista todos los planes |
| POST | `/api/workout-plans/upload` | Subir JSON de plan (multipart) |
| GET | `/api/workout-plans/{id}` | Detalle de un plan |
| POST | `/api/workouts/{id}/retry` | Reintentar workout específico |
| GET | `/api/garmin/status` | Estado de autenticación Garmin |

---

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `SECRET_KEY` | `dev-secret` | Flask secret key |
| `GARTH_HOME` | `/data/garmin_tokens` | Directorio de tokens OAuth |
| `FIT_OUTPUT_FOLDER` | `/data/fit_files/body` | Donde se guardan los .fit |
| `WORKOUT_WATCH_DIR` | `/data/workouts/inbox` | Directorio vigilado |
| `WORKOUT_PROCESSED_DIR` | `/data/workouts/processed` | JSONs procesados |
| `WORKOUT_ERROR_DIR` | `/data/workouts/error` | JSONs con error |
| `DATABASE_URL` | `sqlite:////data/garmin_sync.db` | Base de datos |
| `LEGACY_FIT_SCRIPT` | `/app/legacy/generate_fit.py` | Tu script actual (fallback) |

---

## Migrar tu script actual (Fase 1)

Si ya tienes un script Python que genera `.fit`, tienes dos opciones:

**Opción A:** Copiarlo en `legacy/generate_fit.py` y activar el fallback con la variable `LEGACY_FIT_SCRIPT`.

**Opción B (recomendada):** Adaptar `fit_generator.py` para que use exactamente las mismas llamadas al FIT SDK que ya tienes. Solo tienes que reemplazar el contenido de `generate_body_composition_fit()`.

---

## Estado de autenticación Garmin

La librería `garth` resuelve el histórico problema del "login humano" de Garmin:
- Hace el flujo OAuth completo igual que la app móvil oficial
- Guarda los tokens de forma persistente
- Los renueva automáticamente antes de que expiren
- **Solo necesitas intervención manual si cambias tu contraseña**
