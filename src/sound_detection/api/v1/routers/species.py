from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from sound_detection.db.neo4j import get_neo4j_driver
from sound_detection.knowledge.species_knowledge_service import SpeciesKnowledgeService

router = APIRouter(prefix="/species", tags=["species"])


def get_species_service() -> SpeciesKnowledgeService:
    driver = get_neo4j_driver()
    return SpeciesKnowledgeService(driver)


SpeciesServiceDep = Annotated[SpeciesKnowledgeService, Depends(get_species_service)]


@router.get("/")
async def list_all(
    service: SpeciesServiceDep,
) -> list[dict]:
    all_species = service.list_all_species()
    if not all_species:
        raise HTTPException(status_code=404, detail="none found")
    return all_species


@router.get("/{scientific_name}")
async def get_species(
    scientific_name: str,
    service: SpeciesServiceDep,
) -> dict:
    species = service.get_species_by_scientific_name(scientific_name)
    if not species:
        raise HTTPException(status_code=404, detail="Species not found")
    return species


@router.get("/{scientific_name}/context")
async def get_species_context(
    scientific_name: str,
    service: SpeciesServiceDep,
) -> dict:
    context = service.get_species_context(scientific_name)
    if not context:
        raise HTTPException(status_code=404, detail="Species not found")
    return context
