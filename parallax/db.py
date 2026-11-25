"""Conexao com o Oracle e montagem do banco do Parallax.

O mesmo codigo roda em tres lugares, mudando so as variaveis de ambiente:
  - Oracle Database Free em conteiner (GitHub Actions e docker compose): localhost:1521/FREEPDB1
  - Oracle XE 21c (segunda prova no CI): localhost:1521/XEPDB1
  - Oracle da FIAP, com a conta do proprio RM: oracle.fiap.com.br:1521/ORCL

python-oracledb em modo thin: nao precisa instalar cliente Oracle.
"""
import os
import pathlib

import oracledb

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def config():
    senha = os.environ.get("PARALLAX_PASSWORD")
    if not senha:
        raise SystemExit(
            "Falta a senha do banco: defina PARALLAX_PASSWORD (e PARALLAX_USER e PARALLAX_DSN).\n"
            "A senha nunca vai para o repositorio; veja o README, secao 'Como rodar'."
        )
    return {
        "dsn": os.environ.get("PARALLAX_DSN", "localhost:1521/FREEPDB1"),
        "user": os.environ.get("PARALLAX_USER", "parallax"),
        "password": senha,
    }


_pool = None


def pool():
    global _pool
    if _pool is None:
        c = config()
        _pool = oracledb.create_pool(user=c["user"], password=c["password"], dsn=c["dsn"], min=1, max=4, increment=1)
    return _pool


def fechar():
    global _pool
    if _pool is not None:
        _pool.close(force=True)
        _pool = None


def linhas(cur):
    nomes = [d[0].lower() for d in cur.description]
    return [dict(zip(nomes, r)) for r in cur]


def comandos_do_schema():
    texto = (RAIZ / "parallax" / "schema.sql").read_text(encoding="utf-8")
    blocos, atual = [], []
    for linha in texto.splitlines():
        if linha.strip() == "/":
            bloco = "\n".join(atual).strip()
            if bloco:
                blocos.append(bloco)
            atual = []
        elif not (linha.startswith("--") and not atual):
            atual.append(linha)
    return blocos


def info_banco(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        banner = cur.fetchone()[0]
    except oracledb.DatabaseError:
        # conta sem acesso a v$version (comum em conta de aluno): a view publica responde
        cur.execute("SELECT product || ' ' || version FROM product_component_version WHERE ROWNUM = 1")
        banner = cur.fetchone()[0]
    cur.execute("SELECT sys_context('userenv', 'con_name'), user, sys_context('userenv', 'db_name') FROM dual")
    con, usuario, db = cur.fetchone()
    return {"database": banner, "container": con, "db_name": db, "user": usuario}
