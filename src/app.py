from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
import datetime
import os
import secrets
from dotenv import load_dotenv

db = SQLAlchemy()

def create_app():
    load_dotenv()
    app = Flask(__name__)
    # Set SECRET_KEY in .env to keep people logged in across restarts; a random key works for a demo
    app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    # Database config: SQLite file in the instance/ folder unless DATABASE_URL is set
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///guessing_game.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.context_processor
    def inject_now():
        return {"now": datetime.datetime.now()}

    @app.context_processor
    def inject_buddy_message():
        return {
            "buddy_message": session.get("buddy_message", ""),
            "buddy_hint": session.get("buddy_hint", "")
        }

    # Register Blueprints
    from src.routes.auth import auth_bp
    from src.routes.quiz_base import quiz_bp

    import src.routes.quiz_main
    import src.routes.quiz_personalized
    import src.routes.quiz_ranking

    app.register_blueprint(auth_bp)
    app.register_blueprint(quiz_bp)

    with app.app_context():
        db.create_all()

    from src import music
    os.makedirs(app.instance_path, exist_ok=True)
    music.load_cache(os.path.join(app.instance_path, "years.json"))   # original release years

    return app
