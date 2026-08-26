from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.institutions import router as institutions_router
from app.api.v1.routes.institutions_geo import router as geo_router
from app.api.v1.routes.students import router as students_router
from app.api.v1.routes.categories import router as categories_router
from app.api.v1.routes.rounds import router as rounds_router
from app.api.v1.routes.scoring import router as scoring_router
from app.api.v1.routes.results import router as results_router
from app.api.v1.routes.reports import router as reports_router
from app.api.v1.routes.archive import router as archive_router
from app.api.v1.routes.admin_users import router as admin_users_router
from app.api.v1.routes.audit_logs import router as audit_logs_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(institutions_router)
v1_router.include_router(geo_router)
v1_router.include_router(students_router)
v1_router.include_router(categories_router)
v1_router.include_router(rounds_router)
v1_router.include_router(scoring_router)
v1_router.include_router(results_router)
v1_router.include_router(reports_router)
v1_router.include_router(archive_router)
v1_router.include_router(admin_users_router)
v1_router.include_router(audit_logs_router)
