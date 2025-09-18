from flask import Flask

def create_app():
    app = Flask("RoverAPI")

    from .api.root import bp as root_bp
    from .api.test import bp as test_bp
    from .api.logs import bp as logs_bp
    from .api.doctor import bp as doctor_bp

    # Register blueprints
    app.register_blueprint(root_bp)
    app.register_blueprint(test_bp, url_prefix="/api")
    app.register_blueprint(logs_bp, url_prefix="/api")
    app.register_blueprint(doctor_bp, url_prefix="/api")

    return app
