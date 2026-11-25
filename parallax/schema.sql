-- Parallax MVP, schema Oracle (fase 7).
-- Roda no Oracle Database Free 23ai, no XE 21c e no Oracle da FIAP (19c): nada de BOOLEAN,
-- IF NOT EXISTS nem SELECT sem FROM. Todo objeto leva o prefixo PX_ para conviver com outras
-- tabelas da mesma conta. Cada comando termina numa linha so com "/".
--
-- Camadas, como na fase 6: CONFIAVEL (tabelas com restricao no banco) e REFINADA (views com a
-- regra de negocio). A regra da rota e a da concordancia moram aqui, nao na API.

CREATE TABLE px_usuario (
  usuario_id     VARCHAR2(20)  CONSTRAINT px_pk_usuario PRIMARY KEY,
  login          VARCHAR2(40)  NOT NULL CONSTRAINT px_uq_usuario_login UNIQUE,
  nome           VARCHAR2(120) NOT NULL,
  papel          VARCHAR2(10)  NOT NULL
                 CONSTRAINT px_ck_usuario_papel CHECK (papel IN ('produtor', 'gestor', 'tecnico')),
  registro       VARCHAR2(40),
  propriedade_id VARCHAR2(20),
  senha_hash     VARCHAR2(200) NOT NULL,
  CONSTRAINT px_ck_usuario_produtor CHECK (papel <> 'produtor' OR propriedade_id IS NOT NULL)
)
/
CREATE TABLE px_talhao (
  talhao_id           VARCHAR2(20)  CONSTRAINT px_pk_talhao PRIMARY KEY,
  talhao_nome         VARCHAR2(60)  NOT NULL,
  propriedade_id      VARCHAR2(20)  NOT NULL,
  propriedade_nome    VARCHAR2(120) NOT NULL,
  produtor_pseudonimo VARCHAR2(20)  NOT NULL,
  municipio           VARCHAR2(80),
  uf                  CHAR(2),
  cultura             VARCHAR2(30)  NOT NULL,
  area_ha             NUMBER(8, 2),
  latitude            NUMBER(9, 5),
  longitude           NUMBER(9, 5)
)
/
CREATE SEQUENCE px_seq_analise START WITH 1001
/
CREATE TABLE px_analise (
  analise_id     VARCHAR2(20)  CONSTRAINT px_pk_analise PRIMARY KEY,
  talhao_id      VARCHAR2(20)  NOT NULL CONSTRAINT px_fk_analise_talhao REFERENCES px_talhao,
  sha256_imagem  CHAR(64)      NOT NULL CONSTRAINT px_uq_analise_sha UNIQUE,
  capturado_em   DATE          NOT NULL,
  recebido_em    DATE          DEFAULT SYSDATE NOT NULL,
  severidade_pct NUMBER(5, 2)  NOT NULL
                 CONSTRAINT px_ck_analise_severidade CHECK (severidade_pct BETWEEN 0 AND 100),
  classe         VARCHAR2(20)  NOT NULL
                 CONSTRAINT px_ck_analise_classe CHECK (classe IN ('saudavel', 'inicio_de_doenca', 'doente')),
  praga          VARCHAR2(40)  NOT NULL,
  origem         VARCHAR2(20)  DEFAULT 'carga_fase5' NOT NULL,
  conexao        VARCHAR2(20),
  enviado_por    VARCHAR2(20)  CONSTRAINT px_fk_analise_usuario REFERENCES px_usuario,
  imagem         BLOB,
  imagem_tipo    VARCHAR2(40)
)
/
CREATE INDEX px_ix_analise_talhao_data ON px_analise (talhao_id, capturado_em)
/
CREATE SEQUENCE px_seq_laudo START WITH 1001
/
-- Laudo por TALHAO NA SEMANA (correcao da fase 7): o tecnico avalia o talhao, nao uma foto.
-- praga_semana e severidade_semana_pct guardam o que a tela mostrou na hora do laudo.
CREATE TABLE px_laudo (
  laudo_id              VARCHAR2(20)  CONSTRAINT px_pk_laudo PRIMARY KEY,
  talhao_id             VARCHAR2(20)  NOT NULL CONSTRAINT px_fk_laudo_talhao REFERENCES px_talhao,
  semana_iso            VARCHAR2(8)   NOT NULL,
  tecnico_id            VARCHAR2(20)  NOT NULL CONSTRAINT px_fk_laudo_tecnico REFERENCES px_usuario,
  praga_semana          VARCHAR2(40),
  severidade_semana_pct NUMBER(5, 2),
  praga_confirmada      VARCHAR2(40)  NOT NULL,
  severidade_laudo_pct  NUMBER(5, 2)  NOT NULL
                        CONSTRAINT px_ck_laudo_severidade CHECK (severidade_laudo_pct BETWEEN 0 AND 100),
  concordancia          VARCHAR2(3)   NOT NULL
                        CONSTRAINT px_ck_laudo_concordancia CHECK (concordancia IN ('sim', 'nao')),
  data_laudo            DATE          DEFAULT SYSDATE NOT NULL,
  observacao            VARCHAR2(400),
  origem                VARCHAR2(20)  DEFAULT 'app_mvp' NOT NULL,
  CONSTRAINT px_uq_laudo_talhao_semana UNIQUE (talhao_id, semana_iso)
)
/
CREATE TABLE px_rota (
  semana_iso   VARCHAR2(8)  NOT NULL,
  talhao_id    VARCHAR2(20) NOT NULL CONSTRAINT px_fk_rota_talhao REFERENCES px_talhao,
  ordem        NUMBER(3)    NOT NULL CONSTRAINT px_ck_rota_ordem CHECK (ordem >= 1),
  liberada_por VARCHAR2(20) NOT NULL CONSTRAINT px_fk_rota_usuario REFERENCES px_usuario,
  liberada_em  DATE         DEFAULT SYSDATE NOT NULL,
  CONSTRAINT px_pk_rota PRIMARY KEY (semana_iso, talhao_id),
  CONSTRAINT px_uq_rota_ordem UNIQUE (semana_iso, ordem)
)
/
-- REFINADA. Praga predominante do talhao na semana: a mais frequente entre as fotos com praga
-- identificada; empate desempata pelo nome, para o resultado nao variar entre leituras.
CREATE OR REPLACE VIEW px_v_praga_semana AS
SELECT talhao_id, semana_inicio, praga, fotos
  FROM (SELECT talhao_id,
               TRUNC(capturado_em, 'IW') AS semana_inicio,
               praga,
               COUNT(*) AS fotos,
               ROW_NUMBER() OVER (PARTITION BY talhao_id, TRUNC(capturado_em, 'IW')
                                  ORDER BY COUNT(*) DESC, praga) AS posicao
          FROM px_analise
         WHERE praga <> 'Não identificado'
         GROUP BY talhao_id, TRUNC(capturado_em, 'IW'), praga)
 WHERE posicao = 1
/
CREATE OR REPLACE VIEW px_v_talhao_semana AS
SELECT s.talhao_id,
       s.semana_inicio,
       TO_CHAR(s.semana_inicio, 'IYYY"-W"IW') AS semana_iso,
       s.amostras,
       s.severidade_media_pct,
       s.pct_doentes,
       s.ultima_foto,
       p.praga AS praga_predominante
  FROM (SELECT talhao_id,
               TRUNC(capturado_em, 'IW') AS semana_inicio,
               COUNT(*) AS amostras,
               ROUND(AVG(severidade_pct), 1) AS severidade_media_pct,
               ROUND(100 * SUM(CASE WHEN classe = 'doente' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_doentes,
               MAX(capturado_em) AS ultima_foto
          FROM px_analise
         GROUP BY talhao_id, TRUNC(capturado_em, 'IW')) s
  LEFT JOIN px_v_praga_semana p
    ON p.talhao_id = s.talhao_id AND p.semana_inicio = s.semana_inicio
/
-- A rota: severidade ponderada pela confianca amostral (8 fotos = confianca 1) mais metade da
-- variacao contra a semana anterior. A mesma formula da fase 6, agora com a faixa que o gestor le.
CREATE OR REPLACE VIEW px_v_rota_semanal AS
SELECT b.*,
       ROUND(b.severidade_media_pct * b.confianca_amostral + 0.5 * b.delta_pp, 2) AS score_prioridade,
       CASE
         WHEN ROUND(b.severidade_media_pct * b.confianca_amostral + 0.5 * b.delta_pp, 2) >= 14 THEN 'alta'
         WHEN ROUND(b.severidade_media_pct * b.confianca_amostral + 0.5 * b.delta_pp, 2) >= 8 THEN 'media'
         ELSE 'baixa'
       END AS faixa
  FROM (SELECT w.talhao_id,
               w.semana_inicio,
               w.semana_iso,
               w.amostras,
               w.severidade_media_pct,
               w.pct_doentes,
               w.praga_predominante,
               w.ultima_foto,
               t.talhao_nome,
               t.propriedade_id,
               t.propriedade_nome,
               t.produtor_pseudonimo,
               t.municipio,
               t.cultura,
               ROUND(w.severidade_media_pct - NVL(a.severidade_media_pct, w.severidade_media_pct), 1) AS delta_pp,
               ROUND(LEAST(1, w.amostras / 8), 2) AS confianca_amostral,
               CASE WHEN w.amostras >= 5 THEN 'sim' ELSE 'nao' END AS amostragem_suficiente
          FROM px_v_talhao_semana w
          JOIN px_talhao t ON t.talhao_id = w.talhao_id
          LEFT JOIN px_v_talhao_semana a
            ON a.talhao_id = w.talhao_id AND a.semana_inicio = w.semana_inicio - 7) b
/
-- Concordancia laudo x modelo, no mesmo nivel do laudo (talhao na semana).
CREATE OR REPLACE VIEW px_v_concordancia AS
SELECT COUNT(*) AS laudos,
       NVL(SUM(CASE WHEN concordancia = 'sim' THEN 1 ELSE 0 END), 0) AS concordantes,
       ROUND(100 * SUM(CASE WHEN concordancia = 'sim' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) AS concordancia_pct,
       ROUND(100 * SUM(CASE WHEN concordancia = 'sim' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN praga_semana IS NOT NULL THEN 1 ELSE 0 END), 0), 1) AS concordancia_com_diagnostico_pct,
       NVL(SUM(CASE WHEN praga_semana IS NULL THEN 1 ELSE 0 END), 0) AS sem_diagnostico,
       ROUND(AVG(ABS(severidade_laudo_pct - severidade_semana_pct)), 1) AS erro_medio_severidade_pp
  FROM px_laudo
/
-- O laudo entra por aqui: o banco busca o que a tela mostrou, decide a concordancia e grava.
-- Talhao sem foto na semana: ORA-20001. Segundo laudo no mesmo talhao e semana: ORA-00001.
CREATE OR REPLACE PROCEDURE px_registrar_laudo (
  p_talhao_id   IN  VARCHAR2,
  p_semana_iso  IN  VARCHAR2,
  p_tecnico_id  IN  VARCHAR2,
  p_praga       IN  VARCHAR2,
  p_severidade  IN  NUMBER,
  p_observacao  IN  VARCHAR2,
  p_data_laudo  IN  DATE,
  p_origem      IN  VARCHAR2,
  p_laudo_id    OUT VARCHAR2,
  p_concordancia OUT VARCHAR2,
  p_praga_semana OUT VARCHAR2,
  p_severidade_semana OUT NUMBER
) AS
BEGIN
  BEGIN
    SELECT praga_predominante, severidade_media_pct
      INTO p_praga_semana, p_severidade_semana
      FROM px_v_talhao_semana
     WHERE talhao_id = p_talhao_id AND semana_iso = p_semana_iso;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RAISE_APPLICATION_ERROR(-20001, 'talhao sem foto nesta semana: ' || p_talhao_id || ' ' || p_semana_iso);
  END;

  IF p_praga_semana IS NOT NULL AND p_praga_semana = p_praga THEN
    p_concordancia := 'sim';
  ELSE
    p_concordancia := 'nao';
  END IF;

  p_laudo_id := 'LA-' || LPAD(px_seq_laudo.NEXTVAL, 5, '0');

  INSERT INTO px_laudo (laudo_id, talhao_id, semana_iso, tecnico_id, praga_semana, severidade_semana_pct,
                        praga_confirmada, severidade_laudo_pct, concordancia, data_laudo, observacao, origem)
  VALUES (p_laudo_id, p_talhao_id, p_semana_iso, p_tecnico_id, p_praga_semana, p_severidade_semana,
          p_praga, p_severidade, p_concordancia, NVL(p_data_laudo, SYSDATE), p_observacao, NVL(p_origem, 'app_mvp'));
END;
/
