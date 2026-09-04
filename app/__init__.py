from flask import Flask
from app.config import Config
from app.auth import auth_bp
from app.main import main_bp
from app.documents import documents_bp
from app.analytics import analytics_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(analytics_bp)

    return app
