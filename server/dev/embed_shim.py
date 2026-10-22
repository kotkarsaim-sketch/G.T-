"""Local development embedding server (no Docker required).

Stands in for text-embeddings-inference on developer machines, speaking the
same wire contract the API client expects:

    POST /embed  {"inputs": ["text", ...]}          -> [[float, ...], ...]
    GET  /health                                     -> 200

Model is selectable via the EMBED_MODEL environment variable. Default is
BAAI/bge-small-en-v1.5 (384-dim, English); for cross-lingual testing use
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384-dim).
Production runs TEI with bge-m3 (1024-dim).
"""

import os

from fastapi import FastAPI
from fastembed import TextEmbedding
from pydantic import BaseModel
import uvicorn

MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

app = FastAPI(title="civic-embed-shim", docs_url=None)
# Model load at startup (downloads ~130 MB to the local cache on first run).
_model = TextEmbedding(MODEL)


class EmbedRequest(BaseModel):
    inputs: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL}


@app.post("/embed")
def embed(req: EmbedRequest) -> list[list[float]]:
    return [vec.tolist() for vec in _model.embed(req.inputs)]


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8082, log_level="warning")
