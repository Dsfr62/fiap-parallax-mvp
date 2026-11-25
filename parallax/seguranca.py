"""Senha com PBKDF2-SHA256 da biblioteca padrao. Nenhuma senha em texto no banco nem no repositorio."""
import hashlib
import hmac
import secrets

ITERACOES = 200_000


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${sal.hex()}${dk.hex()}"


def confere(senha: str, guardado: str) -> bool:
    try:
        _, iteracoes, sal_hex, dk_hex = guardado.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(sal_hex), int(iteracoes))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False
