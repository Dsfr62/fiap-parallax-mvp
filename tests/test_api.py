"""O ciclo inteiro pela API, contra o Oracle: papel, rota, foto, liberacao, laudo e retorno.
Os testes seguem a ordem do ciclo; cada um diz o que prova."""
import csv
import datetime as dt
import pathlib
import re
from collections import Counter, defaultdict

import pytest

from imagens import folha

DADOS = pathlib.Path(__file__).resolve().parent.parent / "dados"
ESTADO = {}


def semana(texto):
    d = dt.datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").date()
    return d - dt.timedelta(days=d.weekday())


# ---------- conexao e acesso ----------

def test_health_mostra_o_oracle(entrar):
    r = entrar().get("/api/health")
    assert r.status_code == 200
    corpo = r.json()
    assert "Oracle" in corpo["database"]
    assert re.fullmatch(r"\d{4}-W\d{2}", corpo["reference_week"])
    ESTADO["semanas"] = (corpo["reference_week"], corpo["current_week"])


def test_sem_login_recebe_401(entrar):
    c = entrar()
    assert c.get("/api/route").status_code == 401
    assert c.post("/api/reports", json={"plot_id": "T-009-2", "confirmed_pest": "Ferrugem", "severity_pct": 10}).status_code == 401
    assert c.post("/api/login", json={"login": "gestor", "password": "errada"}).status_code == 401


def test_cada_papel_so_faz_a_sua_parte(entrar):
    produtor, tecnico = entrar("produtor"), entrar("tecnico1")
    assert produtor.get("/api/route").status_code == 403
    assert produtor.post("/api/reports", json={"plot_id": "T-009-2", "confirmed_pest": "Ferrugem", "severity_pct": 10}).status_code == 403
    assert tecnico.post("/api/route/release", json={"plot_ids": ["T-009-2"]}).status_code == 403
    assert tecnico.post("/api/photos", data={"plot_id": "T-009-1", "severity_pct": "5"},
                        files={"photo": ("f.png", folha(), "image/png")}).status_code == 403


def test_produtor_so_ve_os_talhoes_dele(entrar):
    talhoes = entrar("produtor").get("/api/plots").json()
    assert {t["plot_id"] for t in talhoes} == {"T-009-1", "T-009-2"}
    assert len(entrar("gestor").get("/api/plots").json()) == 35


# ---------- rota: a regra mora no banco ----------

def test_rota_vem_ordenada_pela_formula_do_banco(entrar):
    r = entrar("gestor").get("/api/route").json()
    assert r["week"] == ESTADO["semanas"][0]
    itens = r["items"]
    assert len(itens) == 33
    scores = [i["priority_score"] for i in itens]
    assert scores == sorted(scores, reverse=True)
    for i in itens:
        esperado = i["avg_severity_pct"] * i["sample_confidence"] + 0.5 * i["delta_pp"]
        assert abs(esperado - i["priority_score"]) < 0.011, i
        faixa = "alta" if i["priority_score"] >= 14 else "media" if i["priority_score"] >= 8 else "baixa"
        assert i["band"] == faixa
    # os 7 primeiros sao os mesmos da exportacao do Oracle da fase 6 (oracle-data.js, 13/10)
    assert [i["plot_id"] for i in itens[:7]] == ["T-009-2", "T-010-2", "T-008-3", "T-002-1", "T-005-2", "T-011-3", "T-004-1"]
    assert [i["priority_score"] for i in itens[:7]] == [17.4, 16.92, 16.35, 15.7, 14.75, 12.96, 10.23]


def test_rota_bate_com_o_data_lake_da_fase5(entrar):
    """Recalcula em Python, direto do CSV, o talhao do topo; o Oracle tem que dar o mesmo."""
    linhas = list(csv.DictReader(open(DADOS / "analises.csv", encoding="utf-8")))
    ultima = max(semana(l["capturado_em"]) for l in linhas)
    por = defaultdict(list)
    for l in linhas:
        por[(l["talhao_id"], semana(l["capturado_em"]))].append(l)
    fotos = por[("T-009-2", ultima)]
    sev = round(sum(float(f["severidade_pct"]) for f in fotos) / len(fotos), 1)
    doentes = round(100 * sum(f["classe"] == "doente" for f in fotos) / len(fotos), 1)
    praga = sorted(Counter(f["praga"] for f in fotos if f["praga"] != "Não identificado").items(), key=lambda x: (-x[1], x[0]))[0][0]
    topo = entrar("gestor").get("/api/route").json()["items"][0]
    assert (topo["samples"], topo["avg_severity_pct"], topo["diseased_pct"], topo["main_pest"]) == (len(fotos), sev, doentes, praga)


def test_filtro_de_cultura(entrar):
    soja = entrar("gestor").get("/api/route", params={"crop": "Soja"}).json()["items"]
    assert soja and all(i["crop"] == "Soja" for i in soja)
    assert soja[0]["plot_id"] == "T-008-3"


# ---------- foto do produtor ----------

def test_foto_entra_no_oracle_e_repeticao_nao_duplica(entrar):
    produtor = entrar("produtor")
    imagem = folha(semente=1)
    dados = {"plot_id": "T-009-1", "severity_pct": "12.5", "suspected_pest": "Ferrugem"}
    r = produtor.post("/api/photos", data=dados, files={"photo": ("folha.png", imagem, "image/png")})
    assert r.status_code == 201, r.text
    primeira = r.json()
    assert primeira["duplicate"] is False and primeira["photo_id"].startswith("AN-")
    # a fila offline reenviando a mesma foto: o SHA-256 unico devolve a primeira
    r2 = produtor.post("/api/photos", data={**dados, "queued_offline": "true"}, files={"photo": ("folha.png", imagem, "image/png")})
    assert r2.status_code == 200 and r2.json() == {**primeira, "duplicate": True}
    ESTADO["foto"] = (primeira["photo_id"], imagem)
    minhas = produtor.get("/api/photos/mine").json()
    assert minhas[0]["photo_id"] == primeira["photo_id"] and minhas[0]["plot_id"] == "T-009-1"


def test_foto_recusada_pelo_banco_e_pela_regra(entrar):
    produtor = entrar("produtor")
    r = produtor.post("/api/photos", data={"plot_id": "T-009-1", "severity_pct": "142"},
                      files={"photo": ("f.png", folha(semente=2), "image/png")})
    assert r.status_code == 422 and "ORA-02290" in r.json()["oracle"]
    r = produtor.post("/api/photos", data={"plot_id": "T-010-1", "severity_pct": "5"},
                      files={"photo": ("f.png", folha(semente=3), "image/png")})
    assert r.status_code == 403


def test_foto_guardada_como_blob_e_protegida(entrar):
    foto_id, imagem = ESTADO["foto"]
    r = entrar("gestor").get(f"/api/photos/{foto_id}/image")
    assert r.status_code == 200 and r.content == imagem and r.headers["content-type"] == "image/png"
    assert entrar("produtor2").get(f"/api/photos/{foto_id}/image").status_code == 403


def test_foto_nova_aparece_na_previa_da_proxima_rota(entrar):
    r = entrar("gestor").get("/api/route", params={"preview": "true"}).json()
    assert r["week"] == ESTADO["semanas"][1]
    assert r["photos_this_week"] >= 1
    assert "T-009-1" in {i["plot_id"] for i in r["items"]}


# ---------- liberacao, laudo e retorno ----------

def test_gestor_libera_e_tecnico_ve_a_mesma_ordem(entrar):
    gestor = entrar("gestor")
    topo = [i["plot_id"] for i in gestor.get("/api/route").json()["items"][:7]]
    ordem = [topo[1], topo[0]] + topo[2:]  # o gestor trocou as duas primeiras
    r = gestor.post("/api/route/release", json={"plot_ids": ordem})
    assert r.status_code == 200 and r.json()["released"] == 7
    assert gestor.post("/api/route/release", json={"plot_ids": ["T-009-2", "T-009-2"]}).status_code == 422
    visitas = entrar("tecnico1").get("/api/visits").json()
    assert [v["plot_id"] for v in visitas["items"]] == ordem
    assert all(v["report_id"] is None for v in visitas["items"])
    ESTADO["rota"] = visitas["items"]


def test_laudo_concordante_recalcula_a_taxa(entrar):
    antes = entrar("gestor").get("/api/agreement").json()
    visita = next(v for v in ESTADO["rota"] if v["plot_id"] == "T-009-2")
    r = entrar("tecnico1").post("/api/reports", json={"plot_id": "T-009-2", "confirmed_pest": visita["main_pest"],
                                                      "severity_pct": 14, "note": "Ferrugem no terco inferior."})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["agrees"] is True and corpo["screen_pest"] == visita["main_pest"]
    assert corpo["summary"]["reports"] == antes["reports"] + 1
    assert corpo["summary"]["agreeing"] == antes["agreeing"] + 1


def test_laudo_discordante_e_as_recusas(entrar):
    tecnico = entrar("tecnico2")
    visita = next(v for v in ESTADO["rota"] if v["plot_id"] == "T-010-2")
    outra = "Lagarta" if visita["main_pest"] != "Lagarta" else "Oídio"
    r = tecnico.post("/api/reports", json={"plot_id": "T-010-2", "confirmed_pest": outra, "severity_pct": 20})
    assert r.status_code == 201 and r.json()["agrees"] is False
    # segundo laudo no mesmo talhao e semana: a restricao UNIQUE do banco recusa
    r = tecnico.post("/api/reports", json={"plot_id": "T-010-2", "confirmed_pest": outra, "severity_pct": 20})
    assert r.status_code == 409 and "ORA-00001" in r.json()["oracle"]
    # severidade fora de 0 a 100: a CHECK do banco recusa
    r = tecnico.post("/api/reports", json={"plot_id": "T-008-3", "confirmed_pest": "Ferrugem", "severity_pct": 142})
    assert r.status_code == 422 and "ORA-02290" in r.json()["oracle"]
    # talhao fora da rota liberada
    r = tecnico.post("/api/reports", json={"plot_id": "T-012-2", "confirmed_pest": "Ferrugem", "severity_pct": 5})
    assert r.status_code == 422


def test_produtor_recebe_o_retorno_assinado(entrar):
    retorno = entrar("produtor").get("/api/feedback").json()
    assert retorno, "o laudo do T-009-2 devia chegar ao produtor do PP-009"
    r = retorno[0]
    assert r["plot_id"] == "T-009-2" and r["agronomist_name"] == "Rafael Souza" and r["agronomist_registry"]
    assert entrar("produtor2").get("/api/feedback").json()[0]["plot_id"] == "T-010-2"


def test_tecnico_ve_a_visita_feita_e_o_gestor_a_taxa(entrar):
    visitas = entrar("tecnico3").get("/api/visits").json()["items"]
    feitas = {v["plot_id"]: v for v in visitas if v["report_id"]}
    assert set(feitas) == {"T-009-2", "T-010-2"}
    assert feitas["T-009-2"]["agrees"] is True and feitas["T-010-2"]["agrees"] is False
    c = entrar("gestor").get("/api/agreement").json()
    assert c["recent"][0]["plot_name"] and c["agreement_pct"] == pytest.approx(100 * c["agreeing"] / c["reports"], abs=0.06)
