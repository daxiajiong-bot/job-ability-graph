"""Versioned API router."""

from fastapi import APIRouter

from backend.app.api.v1.routes.auth import router as auth_router
from backend.app.api.v1.routes.data_governance import router as data_governance_router
from backend.app.api.v1.routes.documents import router as documents_router
from backend.app.api.v1.routes.intelligence import router as intelligence_router
from backend.app.api.v1.routes.profiles import candidate_router, job_router
from backend.app.api.v1.routes.system import router as system_router
from backend.app.api.v1.routes.users import router as users_router


router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(system_router)
router.include_router(users_router)
router.include_router(documents_router)
router.include_router(data_governance_router)
router.include_router(candidate_router)
router.include_router(job_router)
router.include_router(intelligence_router)
