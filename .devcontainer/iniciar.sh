#!/bin/bash
# Sobe o Oracle Database Free e o Parallax dentro do Codespace. As senhas sao sorteadas na primeira
# vez e ficam no .env do proprio Codespace (fora do git). O banco e montado do zero a cada inicio.
set -eo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  printf 'PARALLAX_DSN=localhost:1521/FREEPDB1\nPARALLAX_USER=parallax\nPARALLAX_PASSWORD=%s\nPARALLAX_DEMO_PASSWORD=%s\nPARALLAX_HOST=0.0.0.0\n' \
    "$(openssl rand -hex 12)" "$(openssl rand -hex 5)" > .env
fi
set -a; . ./.env; set +a
echo "Esperando o Docker do Codespace..."
for i in $(seq 1 60); do docker info > /dev/null 2>&1 && break; sleep 2; done
if docker ps -a --format '{{.Names}}' | grep -q '^parallax-oracle$'; then
  docker start parallax-oracle > /dev/null
else
  docker run -d --name parallax-oracle -p 1521:1521 \
    -e ORACLE_PASSWORD="$PARALLAX_PASSWORD" -e APP_USER=parallax -e APP_USER_PASSWORD="$PARALLAX_PASSWORD" \
    gvenzl/oracle-free:23-slim-faststart > /dev/null
fi
echo "Esperando o Oracle ficar pronto (1 a 3 minutos)..."
until docker exec parallax-oracle healthcheck.sh > /dev/null 2>&1; do sleep 5; done
python -m parallax.setup
setsid nohup python -m parallax > /tmp/parallax.log 2>&1 < /dev/null &
sleep 3
echo
echo "Parallax no ar: aba PORTS, porta 8000 (Parallax)."
echo "Usuarios: gestor, tecnico1, produtor. Senha de demonstracao: $PARALLAX_DEMO_PASSWORD"
echo "(a senha fica no arquivo .env deste Codespace: cat .env)"
