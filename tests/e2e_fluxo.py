"""O ciclo inteiro no navegador, contra a aplicacao rodando sobre o Oracle. Grava os prints e o video.

Uso:  python tests/e2e_fluxo.py http://127.0.0.1:8000 saida
Precisa de PARALLAX_DEMO_PASSWORD (a mesma do setup) e do Chromium do Playwright.

Cada passo confere o que a tela mostra (nao so tira foto): se o ciclo quebrar, o script falha.
"""
import os
import pathlib
import sys

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from imagens import folha  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SAIDA = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "saida")
SENHA = os.environ["PARALLAX_DEMO_PASSWORD"]
PRINTS = SAIDA / "prints"
PRINTS.mkdir(parents=True, exist_ok=True)
passos = []


def foto(page, nome, legenda, alvo=None):
    """Print da area visivel (o topo fixo fica no lugar), com o alvo rolado para dentro dela."""
    if alvo is not None:
        alvo.scroll_into_view_if_needed()
        page.evaluate("window.scrollBy(0, -90)")
    page.wait_for_timeout(600)
    page.screenshot(path=PRINTS / f"{nome}.png")
    passos.append(f"| {nome}.png | {legenda} |")
    print(f"  ok  {nome}: {legenda}")


def entrar(page, login):
    page.request.post(BASE + "/api/logout")
    page.goto(BASE + "/")
    page.get_by_label("Usuário").fill(login)
    page.get_by_label("Senha").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    expect(page.locator("#quem")).to_be_visible()


with sync_playwright() as p:
    navegador = p.chromium.launch(slow_mo=120)
    contexto = navegador.new_context(viewport={"width": 1280, "height": 800}, locale="pt-BR",
                                     timezone_id="America/Sao_Paulo",
                                     record_video_dir=str(SAIDA / "video"), record_video_size={"width": 1280, "height": 800})
    page = contexto.new_page()

    # 1. login
    page.goto(BASE + "/")
    expect(page.get_by_role("heading", name="Entrar")).to_be_visible()
    foto(page, "01-login", "Entrada única; cada papel vê a sua parte do ciclo")

    # 2. produtor manda a foto sem sinal: fica na fila e sai quando o sinal volta
    entrar(page, "produtor")
    expect(page.get_by_role("heading", name="Mandar foto da folha")).to_be_visible()
    page.get_by_label("Talhão").select_option("T-009-2")
    page.locator("#foto").set_input_files({"name": "folha.png", "mimeType": "image/png", "buffer": folha(semente=7)})
    expect(page.locator("#estimativa")).to_contain_text("Estimativa pela cor")
    page.get_by_label("O que você está vendo?").select_option("Ferrugem")
    foto(page, "02-produtor-foto", "Produtor escolhe o talhão, tira a foto e vê a estimativa de lesão pela cor")
    contexto.set_offline(True)
    page.get_by_role("button", name="Enviar foto").click()
    expect(page.locator("#contador")).to_have_text("1")
    foto(page, "03-produtor-sem-sinal", "Sem sinal: a foto fica na fila do aparelho, com o contador")
    contexto.set_offline(False)
    page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.locator("#contador")).to_have_text("0", timeout=20000)
    expect(page.locator("#minhas-fotos")).to_contain_text("chegou à cooperativa")
    expect(page.locator("#minhas-fotos")).to_contain_text("saiu da fila sem sinal")
    foto(page, "04-produtor-foto-chegou", "O sinal voltou: a foto saiu da fila e entrou no Oracle", page.locator("#fila"))

    # 3. gestor: rota da semana, filtro, explicacao, reordenar e liberar
    entrar(page, "gestor")
    expect(page.locator("#rota li").first).to_contain_text("Sítio Água Limpa")
    foto(page, "05-gestor-rota", "Rota da semana ordenada pelo banco, com a faixa de prioridade")
    page.locator("#rota li").first.locator("summary").click()
    expect(page.locator("#rota li").first.locator("details")).to_contain_text("Severidade média")
    foto(page, "06-gestor-por-que", "Por que o talhão está no topo: severidade, amostra e variação, em palavras")
    page.get_by_label("Cultura").select_option("Soja")
    expect(page.locator("#rota li").first).to_contain_text("Fazenda Bela Vista")
    foto(page, "07-gestor-filtro-soja", "Filtro de cultura: o recorte de soja do MVP")
    page.get_by_label("Cultura").select_option("")
    expect(page.locator("#rota li").first).to_contain_text("Sítio Água Limpa")
    page.locator("#rota li").nth(3).get_by_role("button", name="Subir").click()
    page.get_by_role("button", name="Liberar rota").click()
    expect(page.locator("#aviso-rota")).to_contain_text("Rota liberada para o técnico: 7 visitas")
    foto(page, "08-gestor-rota-liberada", "Gestor mudou a ordem e liberou a rota para o técnico")
    page.get_by_label("Prévia da próxima rota").check()
    expect(page.locator("#titulo-rota")).to_contain_text("Prévia")
    expect(page.locator("#rota")).to_contain_text("Sítio Água Limpa")
    foto(page, "09-gestor-previa", "Prévia da próxima rota, já com a foto que o produtor mandou hoje")

    # 4. tecnico: rota liberada, o que a tela mostrou e o laudo
    entrar(page, "tecnico1")
    primeira = page.locator(".visita").first
    expect(primeira).to_contain_text("Sítio Água Limpa")
    expect(primeira).to_contain_text("O que a tela mostrou")
    expect(page.locator(".visita").nth(1).get_by_role("button", name="Registrar laudo desta visita")).to_be_visible()
    foto(page, "10-tecnico-rota", "Técnico vê a rota na ordem liberada; só a próxima visita abre o laudo")
    primeira.get_by_label("Praga confirmada na visita").select_option("Ferrugem")
    primeira.locator(".faixas button").nth(1).click()  # a faixa 10-20%
    primeira.get_by_label("Ajuste fino da severidade").fill("13")
    primeira.get_by_label("Observação").fill("Ferrugem no terço inferior; reaplicar em 7 dias.")
    primeira.get_by_role("button", name="Assinar laudo").click()
    expect(primeira.locator(".aviso")).to_contain_text("Concordou com a tela")
    foto(page, "11-tecnico-laudo", "Laudo assinado: o banco decide a concordância e devolve a taxa nova", primeira.get_by_label("Praga confirmada na visita"))

    # 5. produtor recebe o retorno com nome e registro
    entrar(page, "produtor")
    expect(page.locator("#retornos")).to_contain_text("Rafael Souza")
    foto(page, "12-produtor-retorno", "O produtor recebe a resposta identificada da técnica", page.locator("#retornos"))

    # 6. gestor ve a taxa laudo x modelo
    entrar(page, "gestor")
    expect(page.locator("#laudos-recentes li").first).to_contain_text("Sítio Água Limpa")
    foto(page, "13-gestor-concordancia", "Concordância laudo x modelo, no mesmo nível do laudo (talhão na semana)")

    # 7. a API documentada
    page.goto(BASE + "/docs")
    expect(page.get_by_text("Parallax MVP").first).to_be_visible()
    foto(page, "14-api-docs", "A API documentada (OpenAPI), servida pela própria aplicação")

    video = page.video.path() if page.video else None
    contexto.close()
    navegador.close()

(SAIDA / "prints" / "LEGENDAS.md").write_text(
    "| Arquivo | O que mostra |\n|---|---|\n" + "\n".join(passos) + "\n", encoding="utf-8")
if video:
    destino = SAIDA / "video" / "parallax-ciclo-completo.webm"
    pathlib.Path(video).replace(destino)
    print(f"video: {destino}")
print(f"{len(passos)} passos conferidos")
