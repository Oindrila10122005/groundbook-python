from fastapi import APIRouter

from ..schemas import HealthOut, SettingsOut
from ..services.grounds import buffers, get_venue
from ..services.seed import VENUE
from . import SessionDep, SettingsDep

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsOut, summary="The rules in force: the hold and the live buffer table (read-only)")
def get_settings_(session: SessionDep, settings: SettingsDep) -> SettingsOut:
    return SettingsOut(hold_hours=settings.hold_hours, buffers=buffers(session, get_venue(session, VENUE[0])))


@router.get("/healthz", response_model=HealthOut, summary="Is the app up")
def health() -> HealthOut:
    return HealthOut(status="ok")