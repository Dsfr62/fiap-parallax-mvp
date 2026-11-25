"""Sobe a aplicacao: python -m parallax  (telas em http://127.0.0.1:8000, API em /docs)."""
import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("PARALLAX_HOST", "127.0.0.1")
    porta = int(os.environ.get("PARALLAX_PORT", "8000"))
    print(f"Parallax em http://{'127.0.0.1' if host == '0.0.0.0' else host}:{porta}  (API documentada em /docs)")
    uvicorn.run("parallax.app:app", host=host, port=porta, log_level="info")
