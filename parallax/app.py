"""Parallax MVP: API e telas do ciclo semanal sobre o Oracle.

Ciclo (os nove passos da fase 6, agora executaveis):
  produtor manda a foto do talhao (com fila offline) -> a foto entra no Oracle
  gestor ve a rota da semana ordenada pelo banco, filtra a cultura, reordena e libera
  tecnico segue a rota liberada e registra o laudo do talhao na semana
  o banco decide a concordancia; o produtor recebe o retorno assinado; o gestor ve a taxa

A regra mora nas views e na procedure do schema; a API confere o papel, traduz os nomes para
ingles na fronteira e devolve o erro do banco como veio (422 para restricao, 409 para repeticao).
"""
import datetime as dt
import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import oracledb
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import db, seguranca

WEB = db.RAIZ / "web"
PRAGAS = ["Ferrugem", "Mancha Parda", "Lagarta", "Oídio", "Não identificado"]
TAMANHO_MAX_FOTO = 6 * 1024 * 1024


@asynccontextmanager
async def ciclo_de_vida(app):
    db.pool()
    yield
    db.fechar()


app = FastAPI(title="Parallax MVP", version="1.0.0", lifespan=ciclo_de_vida,
              description="Ciclo semanal de monitoramento de pragas para cooperativas, sobre o Oracle.")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("PARALLAX_SECRET") or secrets.token_hex(32),
                   same_site="lax", max_age=8 * 3600, session_cookie="parallax_sessao")


@app.exception_handler(oracledb.DatabaseError)
async def erro_do_banco(request, exc):
    erro = exc.args[0] if exc.args else None
    codigo = getattr(erro, "code", 0)
    mensagem = str(exc).splitlines()[0]
    if codigo == 1:
        return JSONResponse({"error": "ja existe", "oracle": mensagem}, status_code=409)
    if codigo in (2290, 2291, 1400, 20001, 12899, 1438):
        return JSONResponse({"error": "o banco recusou o dado", "oracle": mensagem}, status_code=422)
    return JSONResponse({"error": "banco indisponivel", "oracle": mensagem}, status_code=503)


# ---------- sessao e papel ----------

def usuario_atual(request: Request):
    u = request.session.get("usuario")
    if not u:
        raise HTTPException(401, "faca login")
    return u


def exige(*papeis):
    def dependencia(u=Depends(usuario_atual)):
        if u["role"] not in papeis:
            raise HTTPException(403, f"papel {u['role']} nao pode usar esta funcao")
        return u
    return dependencia


def semanas(cur):
    cur.execute("""SELECT TO_CHAR(TRUNC(SYSDATE, 'IW') - 7, 'IYYY"-W"IW'),
                          TO_CHAR(TRUNC(SYSDATE, 'IW'), 'IYYY"-W"IW') FROM dual""")
    ref, atual = cur.fetchone()
    return ref, atual


class Login(BaseModel):
    login: str
    password: str


@app.post("/api/login")
def login(dados: Login, request: Request):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT usuario_id, login, nome, papel, registro, propriedade_id, senha_hash
                         FROM px_usuario WHERE login = :login""", login=dados.login.strip().lower())
        linha = cur.fetchone()
    if linha is None or not seguranca.confere(dados.password, linha[6]):
        raise HTTPException(401, "login ou senha incorretos")
    u = {"id": linha[0], "login": linha[1], "name": linha[2], "role": linha[3],
         "registry": linha[4], "farm_id": linha[5]}
    request.session.clear()
    request.session["usuario"] = u
    return u


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(u=Depends(usuario_atual)):
    return u


@app.get("/api/health")
def health():
    with db.pool().acquire() as conn:
        info = db.info_banco(conn)
        cur = conn.cursor()
        ref, atual = semanas(cur)
    return {**info, "reference_week": ref, "current_week": atual}


# ---------- produtor ----------

@app.get("/api/plots")
def plots(u=Depends(usuario_atual)):
    sql = """SELECT talhao_id AS plot_id, talhao_nome AS plot_name, propriedade_id AS farm_id,
                    propriedade_nome AS farm_name, cultura AS crop, area_ha
               FROM px_talhao"""
    params = {}
    if u["role"] == "produtor":
        sql += " WHERE propriedade_id = :farm"
        params["farm"] = u["farm_id"]
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute(sql + " ORDER BY talhao_id", params)
        return db.linhas(cur)


def classe_da_severidade(sev: float) -> str:
    if sev < 5:
        return "saudavel"
    if sev <= 15:
        return "inicio_de_doenca"
    return "doente"


@app.post("/api/photos", status_code=201)
async def enviar_foto(response: Response,
                      plot_id: str = Form(...),
                      severity_pct: float = Form(...),
                      suspected_pest: str = Form("Não identificado"),
                      captured_at: Optional[str] = Form(None),
                      queued_offline: bool = Form(False),
                      photo: UploadFile = File(...),
                      u=Depends(exige("produtor"))):
    conteudo = await photo.read()
    if not conteudo:
        raise HTTPException(422, "foto vazia")
    if len(conteudo) > TAMANHO_MAX_FOTO:
        raise HTTPException(413, "foto maior que 6 MB")
    if suspected_pest not in PRAGAS:
        raise HTTPException(422, f"praga fora da lista: {suspected_pest}")
    sha = hashlib.sha256(conteudo).hexdigest()
    quando = dt.datetime.now()
    if captured_at:
        try:
            quando = dt.datetime.fromisoformat(captured_at.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except ValueError:
            raise HTTPException(422, "captured_at invalido")

    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute("SELECT propriedade_id FROM px_talhao WHERE talhao_id = :t", t=plot_id)
        dono = cur.fetchone()
        if dono is None or dono[0] != u["farm_id"]:
            raise HTTPException(403, "este talhao nao e da sua propriedade")
        # a mesma foto chegando duas vezes (fila offline reenviando) devolve a primeira: idempotente
        cur.execute("SELECT analise_id FROM px_analise WHERE sha256_imagem = :s", s=sha)
        ja = cur.fetchone()
        if ja:
            response.status_code = 200
            return {"photo_id": ja[0], "duplicate": True, "sha256": sha}
        cur.execute("SELECT 'AN-' || LPAD(px_seq_analise.NEXTVAL, 5, '0') FROM dual")
        novo = cur.fetchone()[0]
        cur.setinputsizes(imagem=oracledb.DB_TYPE_BLOB)
        cur.execute("""INSERT INTO px_analise (analise_id, talhao_id, sha256_imagem, capturado_em, severidade_pct,
                                               classe, praga, origem, conexao, enviado_por, imagem, imagem_tipo)
                       VALUES (:id, :talhao, :sha, :quando, :sev, :classe, :praga, 'app_mvp', :conexao,
                               :usuario, :imagem, :tipo)""",
                    id=novo, talhao=plot_id, sha=sha, quando=quando, sev=severity_pct,
                    classe=classe_da_severidade(severity_pct) if 0 <= severity_pct <= 100 else "doente",
                    praga=suspected_pest, conexao="offline_sync" if queued_offline else "online",
                    usuario=u["id"], imagem=conteudo, tipo=photo.content_type or "image/jpeg")
        conn.commit()
    return {"photo_id": novo, "duplicate": False, "sha256": sha}


@app.get("/api/photos/mine")
def minhas_fotos(u=Depends(exige("produtor"))):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT a.analise_id AS photo_id, a.talhao_id AS plot_id, t.talhao_nome AS plot_name,
                              a.capturado_em AS captured_at, a.recebido_em AS received_at,
                              a.severidade_pct AS severity_pct, a.praga AS suspected_pest, a.conexao AS connection
                         FROM px_analise a JOIN px_talhao t ON t.talhao_id = a.talhao_id
                        WHERE a.enviado_por = :u ORDER BY a.recebido_em DESC FETCH FIRST 20 ROWS ONLY""", u=u["id"])
        return db.linhas(cur)


@app.get("/api/photos/{photo_id}/image")
def imagem(photo_id: str, u=Depends(usuario_atual)):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT a.imagem, a.imagem_tipo, t.propriedade_id FROM px_analise a
                         JOIN px_talhao t ON t.talhao_id = a.talhao_id WHERE a.analise_id = :id""", id=photo_id)
        linha = cur.fetchone()
        if linha is None or linha[0] is None:
            raise HTTPException(404, "sem imagem")
        if u["role"] == "produtor" and linha[2] != u["farm_id"]:
            raise HTTPException(403, "foto de outra propriedade")
        return Response(linha[0].read(), media_type=linha[1])


@app.get("/api/feedback")
def retorno(u=Depends(exige("produtor"))):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT l.laudo_id AS report_id, l.talhao_id AS plot_id, t.talhao_nome AS plot_name,
                              l.semana_iso AS week, l.praga_confirmada AS confirmed_pest,
                              l.severidade_laudo_pct AS severity_pct, l.observacao AS note, l.data_laudo AS reported_at,
                              us.nome AS agronomist_name, us.registro AS agronomist_registry
                         FROM px_laudo l JOIN px_talhao t ON t.talhao_id = l.talhao_id
                         JOIN px_usuario us ON us.usuario_id = l.tecnico_id
                        WHERE t.propriedade_id = :farm
                        ORDER BY l.data_laudo DESC FETCH FIRST 10 ROWS ONLY""", farm=u["farm_id"])
        return db.linhas(cur)


# ---------- gestor e tecnico ----------

ROTA_SQL = """SELECT talhao_id AS plot_id, propriedade_nome AS farm_name, talhao_nome AS plot_name,
                     cultura AS crop, municipio AS municipality, produtor_pseudonimo AS grower_alias,
                     amostras AS samples, severidade_media_pct AS avg_severity_pct, pct_doentes AS diseased_pct,
                     praga_predominante AS main_pest, delta_pp, confianca_amostral AS sample_confidence,
                     score_prioridade AS priority_score, faixa AS band,
                     amostragem_suficiente AS enough_samples
                FROM px_v_rota_semanal WHERE semana_iso = :semana"""


def rota_da_semana(cur, semana, cultura=None, limite=None):
    sql, params = ROTA_SQL, {"semana": semana}
    if cultura:
        sql += " AND cultura = :cultura"
        params["cultura"] = cultura
    sql += " ORDER BY score_prioridade DESC, severidade_media_pct DESC, talhao_id"
    if limite:
        sql += " FETCH FIRST :n ROWS ONLY"
        params["n"] = limite
    cur.execute(sql, params)
    itens = db.linhas(cur)
    for i in itens:
        i["enough_samples"] = i["enough_samples"] == "sim"
    return itens


@app.get("/api/route")
def rota(crop: Optional[str] = None, preview: bool = False, u=Depends(exige("gestor"))):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        ref, atual = semanas(cur)
        semana = atual if preview else ref
        itens = rota_da_semana(cur, semana, crop or None)
        cur.execute("""SELECT r.talhao_id, r.ordem, r.liberada_em, us.nome FROM px_rota r
                         JOIN px_usuario us ON us.usuario_id = r.liberada_por
                        WHERE r.semana_iso = :s ORDER BY r.ordem""", s=semana)
        liberada = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM px_analise WHERE capturado_em >= TRUNC(SYSDATE, 'IW')")
        fotos_semana_atual = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT cultura FROM px_talhao ORDER BY cultura")
        culturas = [c[0] for c in cur]
    return {
        "week": semana, "reference_week": ref, "current_week": atual, "preview": preview,
        "crops": culturas, "items": itens, "photos_this_week": fotos_semana_atual,
        "released": [{"plot_id": t, "order": o, "released_at": em, "released_by": quem} for t, o, em, quem in liberada],
    }


class Liberacao(BaseModel):
    plot_ids: list[str] = Field(min_length=1, max_length=20)


@app.post("/api/route/release")
def liberar(dados: Liberacao, u=Depends(exige("gestor"))):
    if len(set(dados.plot_ids)) != len(dados.plot_ids):
        raise HTTPException(422, "talhao repetido na rota")
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        ref, _ = semanas(cur)
        cur.execute("DELETE FROM px_rota WHERE semana_iso = :s", s=ref)
        cur.executemany("""INSERT INTO px_rota (semana_iso, talhao_id, ordem, liberada_por)
                           VALUES (:1, :2, :3, :4)""",
                        [(ref, t, i + 1, u["id"]) for i, t in enumerate(dados.plot_ids)])
        conn.commit()
    return {"week": ref, "released": len(dados.plot_ids)}


@app.get("/api/visits")
def visitas(u=Depends(exige("tecnico", "gestor"))):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        ref, _ = semanas(cur)
        cur.execute("""SELECT r.ordem AS visit_order, v.talhao_id AS plot_id, v.propriedade_nome AS farm_name,
                              v.talhao_nome AS plot_name, v.cultura AS crop, v.municipio AS municipality,
                              v.amostras AS samples, v.severidade_media_pct AS avg_severity_pct,
                              v.praga_predominante AS main_pest, v.faixa AS band,
                              l.laudo_id AS report_id, l.praga_confirmada AS confirmed_pest,
                              l.concordancia AS agrees, lt.nome AS reported_by,
                              (SELECT MAX(a.analise_id) KEEP (DENSE_RANK LAST ORDER BY a.capturado_em)
                                 FROM px_analise a
                                WHERE a.talhao_id = v.talhao_id AND a.imagem IS NOT NULL) AS last_photo_id
                         FROM px_rota r
                         JOIN px_v_rota_semanal v ON v.talhao_id = r.talhao_id AND v.semana_iso = r.semana_iso
                         LEFT JOIN px_laudo l ON l.talhao_id = r.talhao_id AND l.semana_iso = r.semana_iso
                         LEFT JOIN px_usuario lt ON lt.usuario_id = l.tecnico_id
                        WHERE r.semana_iso = :s ORDER BY r.ordem""", s=ref)
        itens = db.linhas(cur)
    for i in itens:
        i["agrees"] = None if i["agrees"] is None else i["agrees"] == "sim"
    return {"week": ref, "pests": PRAGAS, "items": itens}


class Laudo(BaseModel):
    plot_id: str
    confirmed_pest: str
    severity_pct: float
    note: Optional[str] = Field(default=None, max_length=400)


@app.post("/api/reports", status_code=201)
def registrar_laudo(dados: Laudo, u=Depends(exige("tecnico"))):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        ref, _ = semanas(cur)
        cur.execute("SELECT COUNT(*) FROM px_rota WHERE semana_iso = :s AND talhao_id = :t", s=ref, t=dados.plot_id)
        if cur.fetchone()[0] == 0:
            raise HTTPException(422, "talhao fora da rota liberada desta semana")
        saida = [cur.var(str), cur.var(str), cur.var(str), cur.var(oracledb.NUMBER)]
        cur.callproc("px_registrar_laudo", [dados.plot_id, ref, u["id"], dados.confirmed_pest, dados.severity_pct,
                                            dados.note, None, "app_mvp", *saida])
        conn.commit()
        cur.execute("""SELECT laudos AS reports, concordantes AS agreeing, concordancia_pct AS agreement_pct,
                              erro_medio_severidade_pp AS avg_severity_error_pp FROM px_v_concordancia""")
        resumo = db.linhas(cur)[0]
    laudo_id, concordancia, praga_semana, sev_semana = (v.getvalue() for v in saida)
    return {"report_id": laudo_id, "week": ref, "screen_pest": praga_semana, "screen_severity_pct": sev_semana,
            "agrees": concordancia == "sim", "summary": resumo}


@app.get("/api/agreement")
def concordancia(u=Depends(exige("gestor"))):
    with db.pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT laudos AS reports, concordantes AS agreeing, concordancia_pct AS agreement_pct,
                              concordancia_com_diagnostico_pct AS agreement_with_diagnosis_pct,
                              sem_diagnostico AS without_diagnosis,
                              erro_medio_severidade_pp AS avg_severity_error_pp FROM px_v_concordancia""")
        total = db.linhas(cur)[0]
        cur.execute("""SELECT l.laudo_id AS report_id, l.semana_iso AS week, t.propriedade_nome AS farm_name,
                              t.talhao_nome AS plot_name, l.praga_semana AS screen_pest,
                              l.praga_confirmada AS confirmed_pest, l.concordancia AS agrees, us.nome AS agronomist
                         FROM px_laudo l JOIN px_talhao t ON t.talhao_id = l.talhao_id
                         JOIN px_usuario us ON us.usuario_id = l.tecnico_id
                        ORDER BY l.data_laudo DESC FETCH FIRST 6 ROWS ONLY""")
        recentes = db.linhas(cur)
    for r in recentes:
        r["agrees"] = r["agrees"] == "sim"
    return {**total, "recent": recentes}


# ---------- telas ----------

@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(WEB / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


app.mount("/web", StaticFiles(directory=WEB), name="web")
