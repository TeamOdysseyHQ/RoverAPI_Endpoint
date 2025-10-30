from fastapi import APIRouter

# Import all module routers
from app.api.navigation import camera, report, available as nav_available
from app.api.diagnostics import doctor, available as dgt_available
from app.api.science import available as sci_available
from app.api.arm import available as arm_available
from app.api.others import test, available as o_available

# Create main router
router = APIRouter()

# Navigation endpoints -> /api/nav/
router.include_router(camera.router, prefix="/api/nav", tags=["navigation"])
router.include_router(report.router, prefix="/api/nav", tags=["navigation"])
router.include_router(nav_available.router, prefix="/api/nav", tags=["navigation"])

# Diagnostics endpoints -> /api/dgt/
router.include_router(doctor.router, prefix="/api/dgt", tags=["diagnostics"])
router.include_router(dgt_available.router, prefix="/api/dgt", tags=["diagnostics"])

# Science endpoints -> /api/sci/
router.include_router(sci_available.router, prefix="/api/sci", tags=["science"])

# Arm endpoints -> /api/arm/
router.include_router(arm_available.router, prefix="/api/arm", tags=["arm"])

# Other endpoints -> /api/o/
router.include_router(test.router, prefix="/api/o", tags=["other"])
router.include_router(o_available.router, prefix="/api/o", tags=["other"])