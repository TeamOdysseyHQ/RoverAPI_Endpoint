from fastapi import APIRouter

from app.api import ros_endpoints
from app.api.arm import available as arm_available
from app.api.diagnostics import available as dgt_available
from app.api.diagnostics import doctor
from app.api.navigation import (
    available as nav_available,
)

# Import all module routers
from app.api.navigation import (
    camera,
    camera_ws,
    report,
    ros_nav,
)
from app.api.others import available as o_available
from app.api.others import teensy, test
from app.api.science import available as sci_available
from app.api.science import report as sci_reports
from app.api.science import sensor_data as sci_sensor_data
from app.api.science import microscope, microscope_ws

# Create main router
router = APIRouter()

# Navigation endpoints -> /api/nav/
router.include_router(camera.router, prefix="/api/nav", tags=["navigation"])
router.include_router(
    camera_ws.router, prefix="/api/nav", tags=["navigation", "websocket"]
)
router.include_router(report.router, prefix="/api/nav", tags=["navigation"])
router.include_router(nav_available.router, prefix="/api/nav", tags=["navigation"])
router.include_router(ros_nav.router, prefix="/api/nav", tags=["navigation", "ros"])

# Diagnostics endpoints -> /api/dgt/
router.include_router(doctor.router, prefix="/api/dgt", tags=["diagnostics"])
router.include_router(dgt_available.router, prefix="/api/dgt", tags=["diagnostics"])

# Science endpoints -> /api/sci/
router.include_router(sci_available.router, prefix="/api/sci", tags=["science"])
router.include_router(sci_reports.router, prefix="/api/sci", tags=["science"])
router.include_router(
    sci_sensor_data.router, prefix="/api/sci", tags=["science", "sensor", "ros"]
)
router.include_router(
    microscope.router, prefix="/api/sci", tags=["science", "microscope"]
)
router.include_router(
    microscope_ws.router, prefix="/api/sci", tags=["science", "microscope", "websocket"]
)

# Arm endpoints -> /api/arm/
router.include_router(arm_available.router, prefix="/api/arm", tags=["arm"])

# Other endpoints -> /api/o/
router.include_router(test.router, prefix="/api/o", tags=["other"])
router.include_router(teensy.router, prefix="/api/teensy", tags=["other", "teensy"])
router.include_router(o_available.router, prefix="/api/o", tags=["other"])

# ROS bridge endpoints -> /api/
router.include_router(ros_endpoints.router, prefix="/api", tags=["ros"])
