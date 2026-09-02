from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
import os

db = SQLAlchemy()
socketio = SocketIO()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///garmin_sync.db')
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', './out/data/workouts/inbox')
    app.config['FIT_OUTPUT_FOLDER'] = os.environ.get('FIT_OUTPUT_FOLDER', './out/data/fit_files')

    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*",
                      async_mode=os.environ.get('SOCKETIO_ASYNC_MODE', 'threading'))

    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()

    return app
