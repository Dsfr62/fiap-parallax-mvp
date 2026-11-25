"""Os testes rodam contra um Oracle de verdade (no CI, o Oracle Free e o XE em conteiner).
O banco e montado do zero uma vez por rodada, com uma senha de demonstracao sorteada."""
import os
import secrets
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
os.environ.setdefault("PARALLAX_DEMO_PASSWORD", secrets.token_urlsafe(9))

from fastapi.testclient import TestClient  # noqa: E402

from parallax import setup  # noqa: E402
from parallax.app import app  # noqa: E402

SENHA = os.environ["PARALLAX_DEMO_PASSWORD"]


@pytest.fixture(scope="session", autouse=True)
def banco_novo():
    setup.main()
    yield


@pytest.fixture(scope="session")
def entrar():
    clientes = []

    def _entrar(login=None):
        c = TestClient(app)
        c.__enter__()
        clientes.append(c)
        if login:
            r = c.post("/api/login", json={"login": login, "password": SENHA})
            assert r.status_code == 200, r.text
        return c

    yield _entrar
    for c in clientes:
        c.__exit__(None, None, None)
