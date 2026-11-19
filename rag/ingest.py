import uuid
from pathlib import Path
from qdrant_client.models import Distance, PointStruct, VectorParams
from core.config import settings
from rag.retriever import get_embedding_model, get_qdrant_client


def chunk_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_id = "POL-GEN-00"
    buffer: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if buffer:
                sections.append((current_id, " ".join(buffer).strip()))
                buffer = []
            header = stripped.replace("## ", "")
            current_id = header.split(":")[0].strip().replace(" ", "-")
            buffer.append(header)
        elif stripped and not stripped.startswith("# "):
            buffer.append(stripped)

    if buffer:
        sections.append((current_id, " ".join(buffer).strip()))
    return sections


def ingest_policies(policy_dir: Path | None = None) -> int:
    target_dir = policy_dir or Path("data/policies")
    client = get_qdrant_client()
    embedder = get_embedding_model()

    sample_vec = list(embedder.embed(["comprehensive motor insurance schedule"]))[0]
    vector_size = len(sample_vec)

    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    docs: list[dict] = []
    for path in sorted(target_dir.glob("*")):
        if path.suffix.lower() in {".md", ".txt"}:
            content = path.read_text(encoding="utf-8")
            for idx, (clause_id, chunk) in enumerate(chunk_sections(content)):
                docs.append(
                    {
                        "clause_id": clause_id,
                        "source": path.name,
                        "text": chunk,
                        "index": idx,
                    }
                )

    if not docs:
        return 0

    vectors = list(embedder.embed([d["text"] for d in docs]))
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{d['source']}:{d['clause_id']}:{d['index']}")),
            vector=vec.tolist(),
            payload={k: v for k, v in d.items() if k != "index"},
        )
        for d, vec in zip(docs, vectors)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    return len(points)
