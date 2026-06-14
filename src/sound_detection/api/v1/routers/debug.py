from fastapi import APIRouter, Depends
from neo4j import Driver
from pydantic import BaseModel

from sound_detection.db.neo4j import get_neo4j_driver
from sound_detection.knowledge.seed_or_update import SeedOrUpdate

router = APIRouter(prefix="/debug", tags=["debug"])
n4j_dep_driver = Depends(get_neo4j_driver)


class SeedRequest(BaseModel):
    scientific_name: str
    extra_instructions: str | None


def get_seed_service(driver: Driver = n4j_dep_driver) -> SeedOrUpdate:
    return SeedOrUpdate(driver)


gss_dep = Depends(get_seed_service)


@router.post("/seed-species")
def debug_seed_species(
    payload: SeedRequest,
    service: SeedOrUpdate = gss_dep,
) -> dict:
    result = service.seed_or_update(payload.scientific_name, payload.extra_instructions)
    return result
