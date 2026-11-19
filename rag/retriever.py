from functools import lru_cache
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(path=settings.qdrant_local_path)


def search_policy_clauses(query: str, top_k: int = 3) -> list[dict]:
    model = get_embedding_model()
    client = get_qdrant_client()
    if not client.collection_exists(settings.qdrant_collection):
        return []

    query_vector = list(model.embed([query]))[0].tolist()
    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )
    clauses: list[dict] = []
    for point in results.points:
        payload = point.payload or {}
        clauses.append(
            {
                "clause_id": payload.get("clause_id", "POL-GEN-01"),
                "source": payload.get("source", "comprehensive_motor_policy_schedule.md"),
                "text": payload.get("text", ""),
                "score": round(float(point.score or 0.0), 4),
            }
        )
    return clauses
