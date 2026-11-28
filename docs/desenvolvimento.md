# Desenvolvimento do Parallax MVP

O que é: MVP do Parallax (Challenge final da FIAP, fase 7): ciclo semanal de monitoramento de pragas para cooperativas, com a regra de negócio no Oracle.

## Stack
- Python 3.10+, FastAPI, python-oracledb (modo thin), Starlette sessions.
- Telas em HTML, CSS e JS puro (`web/`), sem build.
- Oracle: `parallax/schema.sql` precisa rodar no Free 23ai, no XE 21c e no 19c da FIAP. Nada de BOOLEAN, `IF NOT EXISTS` ou SELECT sem FROM. Todo objeto com prefixo `PX_`.

## Comandos
- Montar o banco: `python -m parallax.setup` (apaga e recria só objetos `PX_`).
- Subir: `python -m parallax` (porta 8000; `/docs` é a API).
- Testes: `python -m pytest -v tests/` (precisam de um Oracle; recriam o banco).
- Ciclo no navegador: `python tests/e2e_fluxo.py http://127.0.0.1:8000 saida`.
- Variáveis: `PARALLAX_DSN`, `PARALLAX_USER`, `PARALLAX_PASSWORD`, `PARALLAX_DEMO_PASSWORD`. Senha nunca no repositório.

## Portão
O workflow `MVP no Oracle` (GitHub Actions) é o portão: testes contra o Oracle Free 23ai e o XE 21c, e o ciclo no navegador com prints e vídeo no 23ai. Docker não roda no Mac do Eduardo: prova pesada sai do CI.

## Armadilhas
- A semana de referência sai do `SYSDATE` do banco; o setup desloca as datas da carga em semanas inteiras.
- Erro do Oracle vira 409 (ORA-00001) ou 422 (CHECK, FK, ORA-20001) no handler de `app.py`.
- `v$version` pode faltar em conta de aluno: `db.info_banco` cai para `product_component_version`.
- Texto que o professor lê: acento, sem travessão nem ponto do meio.
- RM de colega nunca neste repositório (é público): só nomes.
