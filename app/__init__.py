from flask import Flask

def create_app():

    app = Flask("RoverAPI")

    #* Other scripts -> /api/o/
    from .api.others.test import bp as test_bp
    from .api.others.available import bp as o_available_bp
    
    #* Diagnostics -> api/dgt
    from .api.diagnostics.doctor import bp as doctor_bp
    from .api.diagnostics.available import bp as dgt_available_bp
    
    #* Navigation -> End point is api/nav
    from .api.navigation.camera import bp as camera_bp
    from .api.navigation.report import bp as report_bp
    from .api.navigation.available import bp as nav_available_bp

    #* Science -> End point is api/sci
    from .api.science.available import bp as science_available_bp

    #* Arm -> End point is api/arm
    from .api.arm.available import bp as arm_available_bp

    # Register blueprints
    #* Other
    app.register_blueprint(test_bp, url_prefix="/api/o")
    app.register_blueprint(o_available_bp, url_prefix="/api/o")

    #* Diag
    app.register_blueprint(doctor_bp, url_prefix="/api/dgt")
    app.register_blueprint(dgt_available_bp, url_prefix="/api/dgt")

    #* Nav
    app.register_blueprint(camera_bp, url_prefix="/api/nav/")
    app.register_blueprint(report_bp, url_prefix="/api/nav/")
    app.register_blueprint(nav_available_bp, url_prefix="/api/nav/")
    
    #* Sci
    app.register_blueprint(science_available_bp, url_prefix="/api/sci/")

    #* Arm
    app.register_blueprint(arm_available_bp, url_prefix="/api/arm/")

    return app
