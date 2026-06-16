from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from sound_detection.db.neo4j import get_neo4j_driver
from sound_detection.knowledge.rag.pipeline import RAGPipeline
from sound_detection.knowledge.rag.retriever import Retriever

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def get_rag_pipeline() -> RAGPipeline:
    return RAGPipeline(get_neo4j_driver())


dep_rag_pipe = Depends(get_rag_pipeline)


def get_retriever() -> Retriever:
    return Retriever(get_neo4j_driver())


dep_get_ret = Depends(get_retriever)


@router.get("/search")
def search_knowledge(
    query: str = Query(..., min_length=3),
    top_k: int = Query(10, ge=1, le=50),
    retriever: Retriever = dep_get_ret,
) -> list[dict[str, Any]]:
    return retriever.hybrid_search(query, top_k=top_k)


file_dots = File(...)


@router.post("/pdf")
async def upload_pdf(
    file: UploadFile = file_dots,
    scientific_name: str | None = Form(None),
    source_name: str | None = Form(None),
    pipeline: RAGPipeline = dep_rag_pipe,
) -> dict[str, Any]:
    if source_name is None:
        source_name = file.filename

    contents = await file.read()
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(contents)

    success = pipeline.ingest_pdf(
        file_path=temp_path,
        source_name=source_name or file.filename or "uploaded_pdf",
        scientific_name=scientific_name,
    )
    return {"success": success, "source_name": source_name, "scientific_name": scientific_name}


@router.post("/chunks/link")
def link_chunk(
    scientific_name: str = Form(...),
    chunk_index: int = Form(...),
    source_name: str | None = Form(None),
    pipeline: RAGPipeline = dep_rag_pipe,
) -> dict[str, str]:
    pipeline.link_chunk_to_species(
        scientific_name=scientific_name,
        chunk_index=chunk_index,
        source_name=source_name,
    )
    return {"status": "linked"}


@router.post("/chunks/unlink")
def unlink_chunks(
    scientific_name: str = Form(...),
    chunk_index: int | None = Form(None),
    source_name: str | None = Form(None),
    start_index: int | None = Form(None),
    end_index: int | None = Form(None),
    pipeline: RAGPipeline = dep_rag_pipe,
) -> dict[str, str]:
    pipeline.unlink_chunks_from_species(
        scientific_name=scientific_name,
        chunk_index=chunk_index,
        source_name=source_name,
        start_index=start_index,
        end_index=end_index,
    )
    return {"status": "unlinked"}
