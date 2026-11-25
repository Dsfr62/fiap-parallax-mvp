# Parallax, MVP funcional (Challenge final, fase 7)

O Parallax organiza a semana da equipe técnica de uma cooperativa agrícola. O produtor manda a foto da folha, o banco ordena as propriedades que precisam de visita, o técnico registra o laudo e o produtor recebe a resposta assinada. A cooperativa mede, talhão por talhão, se o que o sistema apontou foi o que o técnico encontrou.

Projeto do grupo para o Enterprise Challenge e o Startup One da FIAP (Engenharia de Software, 4º ano, turma 4ESOA), com a Oracle como empresa parceira.

[![MVP no Oracle](https://github.com/Dsfr62/fiap-parallax-mvp/actions/workflows/mvp.yml/badge.svg)](https://github.com/Dsfr62/fiap-parallax-mvp/actions/workflows/mvp.yml)

## O ciclo que roda

| Passo | Quem | O que acontece | Onde mora a regra |
|---|---|---|---|
| 1 | Produtor | Escolhe o talhão, tira a foto e vê a estimativa de lesão pela cor. Sem sinal, a foto fica na fila do aparelho e sai sozinha quando o sinal volta. | Fila no IndexedDB; a foto vai para um BLOB no Oracle, com SHA-256 único (reenvio não duplica) |
| 2 | Coordenação | Vê a rota da semana já ordenada, com a faixa de prioridade e o porquê de cada talhão em palavras. Filtra a cultura, reordena (setas ou arrastar) e libera. | View `px_v_rota_semanal` |
| 3 | Técnico | Segue a rota na ordem liberada, vê o que a tela mostrou do talhão e assina o laudo em poucos toques. | Procedure `px_registrar_laudo` decide a concordância |
| 4 | Produtor | Recebe o retorno com o nome e o registro de quem olhou. | Tabela `px_laudo` |
| 5 | Coordenação | Acompanha a taxa laudo × modelo, no mesmo nível do laudo (o talhão na semana). | View `px_v_concordancia` |

## Onde entra a Oracle

| Recurso | Uso no MVP |
|---|---|
| Oracle Database (Free 23ai, XE 21c ou o servidor da FIAP) | Banco do ciclo inteiro: o mesmo `schema.sql` roda nos três |
| Views da camada refinada | A ordem da rota (severidade × confiança da amostra + variação na semana), a praga predominante e a concordância. A API não ordena nem calcula |
| PL/SQL | `px_registrar_laudo` busca o que a tela mostrou, decide a concordância e grava, numa transação |
| Restrições CHECK, UNIQUE e FOREIGN KEY | Severidade de 0 a 100, um laudo por talhão na semana, foto sem duplicata, papel válido. O erro do banco volta para a tela como veio (ORA-02290, ORA-00001) |
| Sequences | Identificador de foto e de laudo sem colisão entre técnicos |
| BLOB | A foto do produtor guardada no banco, servida só a quem pode ver |
| python-oracledb (modo thin) | Driver oficial, sem instalar cliente Oracle; roda em Windows, Mac e Linux |

## Como rodar

São quatro caminhos, com o mesmo código. Em todos, a senha fica no seu terminal (ou num `.env` que não vai para o git), nunca no repositório.

### A. No navegador, sem instalar nada (GitHub Codespaces)

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Dsfr62/fiap-parallax-mvp)

Clique no botão, entre com a sua conta do GitHub e espere de 3 a 5 minutos: o Codespace sobe o Oracle Database Free e o Parallax sozinhos. Quando o terminal mostrar "Parallax no ar", abra a aba PORTS, porta 8000. A senha dos usuários de demonstração aparece no terminal (e fica no `.env` do Codespace). Usa a cota gratuita do GitHub; pare o Codespace ao terminar.

### B. Com o Oracle da FIAP (sem Docker)

Precisa de Python 3.10 ou mais novo e da conta Oracle do seu RM.

```bash
git clone https://github.com/Dsfr62/fiap-parallax-mvp.git
cd fiap-parallax-mvp
python -m venv .venv
# Windows: .venv\Scripts\activate    Mac e Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Defina as variáveis (no Windows, troque `export` por `set`):

```bash
export PARALLAX_DSN=oracle.fiap.com.br:1521/ORCL
export PARALLAX_USER=RM000000            # o seu RM
export PARALLAX_PASSWORD='sua senha Oracle'
export PARALLAX_DEMO_PASSWORD='escolha uma senha para os usuários de demonstração'
python -m parallax.setup                 # cria as tabelas PX_ na sua conta e carrega os dados
python -m parallax                       # abre em http://127.0.0.1:8000
```

O setup só apaga e recria objetos com o prefixo `PX_`; o resto da sua conta não muda.

### C. Com Docker

Crie o `.env` a partir do `.env.exemplo` (só `PARALLAX_PASSWORD` e `PARALLAX_DEMO_PASSWORD`) e rode `docker compose up`. Sobe o Oracle Database Free e a aplicação em http://127.0.0.1:8000.

### D. No GitHub Actions

Cada push roda o workflow [MVP no Oracle](.github/workflows/mvp.yml): sobe o Oracle Database Free 23ai e o Oracle XE 21c em contêiner, monta o banco, roda os testes da API contra os dois e, no 23ai, percorre o ciclo inteiro num navegador de verdade, gravando os prints e o vídeo (artefato `evidencias-FREEPDB1`).

## Usuários de demonstração

A senha de todos é a `PARALLAX_DEMO_PASSWORD` do setup (se você não definir, o setup sorteia uma e mostra uma vez no terminal).

| Usuário | Papel | Vê |
|---|---|---|
| `produtor` | Produtor do Sítio Água Limpa (talhões T-009-1 e T-009-2) | Mandar foto, fila sem sinal, resposta da técnica |
| `produtor2` | Produtor da Fazenda Santo Antônio | O mesmo, só da propriedade dele |
| `gestor` | Coordenação técnica | Rota, filtro, liberação, prévia, concordância |
| `tecnico1`, `tecnico2`, `tecnico3` | Técnicos (registro fictício) | Rota liberada e laudo |

A API documentada fica em http://127.0.0.1:8000/docs.

## Dados

Os 35 talhões, as 640 fotos analisadas e os 60 laudos vêm do data lake da fase 5 (camada confiável), sintéticos e com o produtor pseudonimizado. As datas andam em semanas inteiras para a última semana de fotos virar a semana passada: a rota de segunda sai dela, e a foto que o produtor manda hoje entra na prévia da próxima rota. Os laudos antigos viram laudos do talhão na semana (o mais recente de cada um), e os da semana de referência ficam fora, para a demonstração começar com a rota ainda sem visita.

A ordem da rota calculada pelo banco reproduz a exportação do Oracle da fase 6: os sete primeiros talhões e as sete pontuações são os mesmos (há um teste que confere).

## O que mudou desde a fase 6

| Compromisso do roadmap da fase 6 | Estado no MVP |
|---|---|
| Laudo por talhão na semana, comparado com a praga predominante | Feito: `px_laudo` com UNIQUE (talhão, semana) e a concordância decidida no banco contra a praga que a tela mostrou |
| Autenticação por papel | Feito: produtor, coordenação e técnico, com sessão assinada e senha em PBKDF2; cada rota da API confere o papel (401 e 403 testados) |
| A rota não pode sair com a semana anterior | Feito: as views são calculadas na leitura, não há cópia para ficar velha; a semana de referência sai do relógio do banco |
| Filtro de cultura na rota | Feito |
| App do técnico com offline real | Parcial: o offline real está no app do produtor (fila e casca das telas guardadas no aparelho); no técnico, fica para depois do MVP |
| Upload da foto | Feito no Oracle (BLOB). O OCI Object Storage fica para a escala, quando o volume de fotos pedir |
| API atrás do ORDS no Autonomous Database | Não feito: a API continua em Python, fina, com a regra no banco; trocar pelo ORDS não muda a regra |
| Usabilidade do teste da fase 6 | Feito: faixa (alta, média, baixa) no lugar do número, explicação ao tocar, último talhão pré-selecionado, arrastar na rota e ajuste fino da severidade |
| Retorno por WhatsApp | Não feito: o retorno chega na tela do produtor |

## Limites, ditos com clareza

- A estimativa de lesão na foto é pela cor (verde contra amarelo e marrom), feita no aparelho. Não é um modelo treinado; a praga é a que o produtor marca, e quem confirma é o técnico.
- Os dados são sintéticos (fase 5). Os registros dos técnicos são fictícios.
- O teste com usuários e o modelo de negócio estão no documento consolidado do grupo, não neste repositório.

## Estrutura

```
parallax/schema.sql   tabelas, views e a procedure (Oracle)
parallax/setup.py     monta o banco e carrega os dados
parallax/app.py       a API (FastAPI) e as telas
web/                  as três telas, a fila offline e o service worker
dados/                talhões, fotos, laudos e usuários de demonstração
tests/test_api.py     o ciclo pela API, contra o Oracle
tests/e2e_fluxo.py    o ciclo no navegador, com prints e vídeo
```

## Grupo

Bruno Reis Lago, Eduardo Sávio Fonseca Resende, Gustavo Vieira da Silva, João Guilherme Mazur Ferreira e Marina da Conceição Pereira.

A base é o trabalho do grupo nas fases anteriores: o data lake da fase 5 e o protótipo, a prova de conceito e o roadmap da fase 6. Este MVP foi escrito com a ajuda de um assistente de código com IA (Claude Code), revisado e conduzido pelo grupo.
