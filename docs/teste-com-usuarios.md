# Teste do MVP com usuários (Parte 2)

O enunciado pede pelo menos 3 pessoas do público-alvo usando o MVP de verdade, com o registro das dificuldades, do feedback e dos ajustes feitos depois. Este roteiro repete as tarefas da fase 6, para comparar.

## Quem testa

Uma pessoa por papel, de preferência as mesmas três da fase 6:

| Código | Perfil | Usa a tela |
|---|---|---|
| P1 | Coordenação técnica de cooperativa (ou quem organiza visita de campo) | Coordenação (`gestor`) |
| P2 | Técnico ou agrônomo de campo | Técnico (`tecnico1`) |
| P3 | Produtor rural | Produtor (`produtor`) |

Só vale gente de verdade. Resposta inventada não entra no documento.

## Antes de começar

1. Rode o MVP pelo README (caminho A, com o Oracle da FIAP) e faça `python -m parallax.setup` para começar com o banco limpo.
2. Para o produtor testar no celular: suba com `PARALLAX_HOST=0.0.0.0`, conecte o celular na mesma rede e abra `http://IP-do-computador:8000`.
3. Não explique a tela antes. Leia só a tarefa e marque o tempo.

## Tarefas (na ordem do ciclo)

| Nº | Quem | Tarefa lida em voz alta | Concluiu quando |
|---|---|---|---|
| 1 | P3 | "Mande uma foto de uma folha do Talhão 2, sem sinal" (modo avião ligado) | Contador mostra 1 foto esperando |
| 2 | P3 | "Volte o sinal e me diga se a foto chegou na cooperativa" | Lê "chegou à cooperativa" |
| 3 | P1 | "Me explique por que o primeiro talhão está no topo" | Explica com as palavras da tela |
| 4 | P1 | "Suba a quarta propriedade uma posição e libere a rota" | Lê "Rota liberada para o técnico" |
| 5 | P2 | "Registre o laudo da primeira visita: ferrugem, 13% de severidade" | Lê "Laudo assinado" |
| 6 | P3 | "Encontre a resposta da técnica" | Lê o nome e o registro |

## Ficha por pessoa (preencher na hora)

| Tarefa | Concluiu? (sim, com ajuda, não) | Tempo | Facilidade (1 a 5) | O que travou | O que a pessoa disse (literal) |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| ... | | | | | |

No fim, duas perguntas abertas:

- "Isso resolve o seu problema da semana? Por quê?"
- "O que você mudaria primeiro?"

## Depois do teste

- Dificuldades e feedback de cada pessoa, com as falas literais.
- O que foi ajustado no MVP por causa do teste (o commit vai junto) e o que ficou para depois.
- A análise: o MVP resolve o problema da fase 5 (a cooperativa não sabe para onde mandar o técnico primeiro e não mede se o diagnóstico acertou)?
