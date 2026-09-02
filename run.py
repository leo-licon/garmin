from app import create_app, socketio, db
from app.watcher import start_watcher

app = create_app()

with app.app_context():
    db.create_all()

# Start directory watcher as a background thread
start_watcher(app, socketio)

if __name__ == '__main__':
    # Local dev: Flask-SocketIO built-in server (no gunicorn needed)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
    # use_reloader=False because the watcher thread conflicts with the reloader
