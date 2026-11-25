"""Monta o banco do Parallax do zero: apaga os objetos PX_, cria o schema e carrega os dados.

Uso:  python -m parallax.setup

Os dados vem do data lake da fase 5 (35 talhoes, 640 fotos, 60 laudos, todos sinteticos e com
produtor pseudonimizado). As datas andam em semanas inteiras para a ultima semana de fotos virar
a semana passada: a rota de segunda sai dela, e a foto que o produtor manda hoje cai na semana
corrente. Os laudos da semana de referencia ficam fora da carga, para a demonstracao comecar com
a rota ainda sem visita.

Senha dos usuarios de demonstracao: PARALLAX_DEMO_PASSWORD; sem ela, o setup sorteia uma e mostra
no terminal uma vez (o banco so guarda o hash).
"""
import csv
import datetime as dt
import os
import secrets
import sys

import oracledb

from . import db, seguranca

DADOS = db.RAIZ / "dados"


def ler(nome):
    with open(DADOS / nome, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def apagar_objetos(cur):
    cur.execute(r"""
        SELECT object_type, object_name FROM user_objects
         WHERE object_name LIKE 'PX\_%' ESCAPE '\'
           AND object_type IN ('TABLE', 'VIEW', 'SEQUENCE', 'PROCEDURE')""")
    ordem = {"VIEW": 0, "PROCEDURE": 1, "TABLE": 2, "SEQUENCE": 3}
    objetos = sorted(cur.fetchall(), key=lambda o: ordem[o[0]])
    for tipo, nome in objetos:
        extra = " CASCADE CONSTRAINTS PURGE" if tipo == "TABLE" else ""
        cur.execute(f'DROP {tipo} "{nome}"{extra}')
    return len(objetos)


def inicio_da_semana(d):
    return d - dt.timedelta(days=d.weekday())


def main():
    senha_demo = os.environ.get("PARALLAX_DEMO_PASSWORD")
    sorteada = senha_demo is None
    if sorteada:
        senha_demo = secrets.token_urlsafe(9)

    talhoes, analises, laudos, usuarios = ler("talhoes.csv"), ler("analises.csv"), ler("laudos.csv"), ler("usuarios.csv")

    with db.pool().acquire() as conn:
        cur = conn.cursor()
        info = db.info_banco(conn)
        print(f"Banco: {info['database']} | {info['container']} | usuario {info['user']}")

        print(f"Apagados {apagar_objetos(cur)} objetos PX_ antigos")
        comandos = db.comandos_do_schema()
        for c in comandos:
            cur.execute(c)
        cur.execute("SELECT object_name FROM user_objects WHERE object_type = 'PROCEDURE' AND object_name = 'PX_REGISTRAR_LAUDO' AND status = 'VALID'")
        if cur.fetchone() is None:
            sys.exit("A procedure PX_REGISTRAR_LAUDO compilou com erro (veja USER_ERRORS).")
        print(f"Schema criado: {len(comandos)} comandos")

        cur.execute("SELECT TRUNC(SYSDATE, 'IW') FROM dual")
        semana_atual = cur.fetchone()[0].date()
        semana_ref = semana_atual - dt.timedelta(days=7)
        ultima = max(dt.datetime.strptime(a["capturado_em"], "%Y-%m-%d %H:%M:%S") for a in analises)
        deslocamento = semana_ref - inicio_da_semana(ultima.date())
        print(f"Datas andam {deslocamento.days} dias: a ultima semana de fotos vira a de {semana_ref:%d/%m/%Y}")

        cur.executemany(
            """INSERT INTO px_talhao (talhao_id, talhao_nome, propriedade_id, propriedade_nome, produtor_pseudonimo,
                                      municipio, uf, cultura, area_ha, latitude, longitude)
               VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11)""",
            [(t["talhao_id"], t["talhao_nome"], t["propriedade_id"], t["propriedade_nome"], t["produtor_pseudonimo"],
              t["municipio"], t["uf"], t["cultura"], float(t["area_ha"]), float(t["latitude"]), float(t["longitude"]))
             for t in talhoes])

        cur.executemany(
            """INSERT INTO px_usuario (usuario_id, login, nome, papel, registro, propriedade_id, senha_hash)
               VALUES (:1, :2, :3, :4, :5, :6, :7)""",
            [(u["usuario_id"], u["login"], u["nome"], u["papel"], u["registro"] or None, u["propriedade_id"] or None,
              seguranca.gerar_hash(senha_demo)) for u in usuarios])

        talhao_da_analise, semana_da_analise = {}, {}
        lote = []
        for a in analises:
            quando = dt.datetime.strptime(a["capturado_em"], "%Y-%m-%d %H:%M:%S") + deslocamento
            talhao_da_analise[a["analysis_id"]] = a["talhao_id"]
            semana_da_analise[a["analysis_id"]] = inicio_da_semana(quando.date())
            lote.append((a["analysis_id"], a["talhao_id"], a["sha256_imagem"], quando, quando,
                         float(a["severidade_pct"]), a["classe"], a["praga"], a["conexao"]))
        cur.executemany(
            """INSERT INTO px_analise (analise_id, talhao_id, sha256_imagem, capturado_em, recebido_em,
                                       severidade_pct, classe, praga, conexao)
               VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)""", lote)

        # laudo historico vira laudo do talhao na semana: o mais recente de cada talhao e semana
        escolhidos = {}
        for l in laudos:
            semana = semana_da_analise[l["analysis_id"]]
            if semana >= semana_ref:
                continue
            chave = (talhao_da_analise[l["analysis_id"]], semana)
            if chave not in escolhidos or (l["data_laudo"], l["laudo_id"]) > (escolhidos[chave]["data_laudo"], escolhidos[chave]["laudo_id"]):
                escolhidos[chave] = l
        for (talhao, semana), l in sorted(escolhidos.items()):
            quando = dt.datetime.strptime(l["data_laudo"], "%Y-%m-%d") + deslocamento + dt.timedelta(hours=10)
            semana_iso = f"{semana.isocalendar()[0]}-W{semana.isocalendar()[1]:02d}"
            saida = [cur.var(str), cur.var(str), cur.var(str), cur.var(oracledb.NUMBER)]
            cur.callproc("px_registrar_laudo", [talhao, semana_iso, l["agronomo_id"], l["praga_confirmada"],
                                                float(l["severidade_laudo_pct"]), l["observacao"], quando, "carga_fase5", *saida])
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM px_analise")
        n_analises = cur.fetchone()[0]
        cur.execute("SELECT laudos, concordantes, concordancia_pct FROM px_v_concordancia")
        n_laudos, concordantes, pct = cur.fetchone()
        print(f"Carga: {len(talhoes)} talhoes, {n_analises} fotos, {len(usuarios)} usuarios, "
              f"{n_laudos} laudos por talhao na semana ({concordantes} concordantes, {pct}%)")

    db.fechar()
    if sorteada:
        print(f"\nSenha dos usuarios de demonstracao (so aparece agora): {senha_demo}")
    print("Pronto. Suba a aplicacao com: python -m parallax")


if __name__ == "__main__":
    main()
