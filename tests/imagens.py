"""Imagens de teste geradas no codigo (PNG sem dependencia): uma folha verde com manchas marrons."""
import math
import struct
import zlib


def png(largura, altura, pixel):
    linhas = bytearray()
    for y in range(altura):
        linhas.append(0)
        for x in range(largura):
            linhas.extend(pixel(x, y))
    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    cab = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cab) + bloco(b"IDAT", zlib.compress(bytes(linhas), 9)) + bloco(b"IEND", b"")


def folha(semente=0, manchas=9, lado=240):
    """Folha eliptica verde sobre fundo cinza, com `manchas` lesoes marrons. `semente` muda os bytes."""
    centros = [(lado * (0.32 + 0.36 * ((i * 37 + semente * 11) % 10) / 10),
                lado * (0.30 + 0.40 * ((i * 53 + semente * 7) % 10) / 10)) for i in range(manchas)]
    def pixel(x, y):
        dx, dy = (x - lado / 2) / (lado * 0.42), (y - lado / 2) / (lado * 0.26)
        if dx * dx + dy * dy > 1:
            return (200, 200, 200 - (semente % 5))
        for cx, cy in centros:
            if math.hypot(x - cx, y - cy) < lado * 0.045:
                return (140, 95, 35)
        return (60, 140 + (y % 20), 55)
    return png(lado, lado, pixel)
