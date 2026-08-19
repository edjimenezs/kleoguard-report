#!/usr/bin/env python3
"""Genera la fotografía pública del mercado desde los boletines ODEPA/AFECH.

No accede a información privada. Sólo descarga los XLS públicos del boletín
semanal y calcula promedios simples por feria y jornada para la vista web.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from openpyxl import load_workbook


BOLETIN_URL = (
    "https://www.odepa.gob.cl/contenidos-rubro/boletines-del-rubro/"
    "boletin-semanal-de-precios-asoc-gremial-de-ferias-ganaderas"
)
DESTINO = Path(__file__).resolve().parents[1] / "market-data.json"
MAX_BOLETINES = 10
SHEET_NAME = "Promedio (5 primeros precios)"
CATEGORIAS = (
    "Novillo Gordo", "Novillo Engorda", "Vaca Gorda", "Vaca Engorda",
    "Vaquilla Gorda", "Vaquilla Engorda", "Toros", "Terneros", "Terneras",
)


def texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def descargar(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "KleoGuard-public-market/1.0"})
    with urlopen(request, timeout=45) as response:  # nosec B310: source is fixed public ODEPA.
        return response.read()


def links_xls() -> list[str]:
    pagina = descargar(BOLETIN_URL).decode("utf-8", errors="ignore")
    encontrados = re.findall(r'''href=["']([^"']+\.xlsx(?:\?[^"']*)?)["']''', pagina, flags=re.I)
    unicos: list[str] = []
    for enlace in encontrados:
        enlace = urljoin(BOLETIN_URL, enlace.replace("&amp;", "&"))
        if enlace not in unicos:
            unicos.append(enlace)
    if not unicos:
        raise RuntimeError("ODEPA no entregó enlaces XLS en la página del boletín.")
    return unicos[:MAX_BOLETINES]


def numero(valor: object) -> float | None:
    if isinstance(valor, (int, float)):
        return float(valor) if float(valor) > 0 else None
    try:
        convertido = float(str(valor).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    return convertido if convertido > 0 else None


def leer_boletin(contenido: bytes, url: str) -> list[dict[str, object]]:
    from io import BytesIO

    libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    if SHEET_NAME not in libro.sheetnames:
        raise RuntimeError(f"El XLS cambió: no existe la hoja {SHEET_NAME!r}.")
    hoja = libro[SHEET_NAME]
    encabezado_fila = None
    encabezados: list[str] = []
    for indice, fila in enumerate(hoja.iter_rows(max_row=20, values_only=True), start=1):
        candidatos = [texto(celda) for celda in fila]
        if "Feria" in candidatos and "Fecha" in candidatos:
            encabezado_fila, encabezados = indice, candidatos
            break
    if encabezado_fila is None:
        raise RuntimeError("No se encontró el encabezado Feria/Fecha en el XLS.")
    columnas = {nombre: posicion for posicion, nombre in enumerate(encabezados)}
    registros: list[dict[str, object]] = []
    for fila in hoja.iter_rows(min_row=encabezado_fila + 1, values_only=True):
        feria = texto(fila[columnas["Feria"]]) if columnas["Feria"] < len(fila) else ""
        if feria.lower().startswith("fuente"):
            break
        fecha = fila[columnas["Fecha"]] if columnas["Fecha"] < len(fila) else None
        if not feria or not isinstance(fecha, (date, datetime)):
            continue
        fecha_iso = fecha.date().isoformat() if isinstance(fecha, datetime) else fecha.isoformat()
        comuna = texto(fila[columnas.get("Comuna", -1)]) if "Comuna" in columnas else ""
        for categoria in CATEGORIAS:
            posicion = columnas.get(categoria)
            if posicion is None or posicion >= len(fila):
                continue
            valor = numero(fila[posicion])
            if valor is not None:
                registros.append({"categoria": categoria, "feria": feria, "comuna": comuna, "fecha": fecha_iso, "valor": valor, "url": url})
    return registros


def promedio_por_fecha(registros: list[dict[str, object]]) -> list[dict[str, object]]:
    agrupado: dict[str, list[float]] = defaultdict(list)
    for registro in registros:
        agrupado[str(registro["fecha"])].append(float(registro["valor"]))
    return [{"fecha": fecha, "valor": round(mean(valores)), "ferias": len(valores)} for fecha, valores in sorted(agrupado.items())]


def historia_operador(registros: list[dict[str, object]], operador: str) -> list[dict[str, object]]:
    return promedio_por_fecha([registro for registro in registros if operador in texto(registro["feria"]).lower()])


def ultimo(historial: list[dict[str, object]]) -> dict[str, object] | None:
    return historial[-1] if historial else None


def construir() -> dict[str, object]:
    registros_por_clave: dict[tuple[str, str, str, str], dict[str, object]] = {}
    fuentes: list[str] = []
    errores: list[str] = []
    for url in links_xls():
        try:
            for registro in leer_boletin(descargar(url), url):
                clave = (str(registro["categoria"]), str(registro["feria"]), str(registro["comuna"]), str(registro["fecha"]))
                registros_por_clave[clave] = registro
            fuentes.append(url)
        except Exception as exc:
            errores.append(f"{url}: {exc}")
    registros = list(registros_por_clave.values())
    if not registros:
        raise RuntimeError("No fue posible extraer datos de ningún boletín ODEPA/AFECH.")
    categorias: dict[str, object] = {}
    for categoria in CATEGORIAS:
        de_categoria = [registro for registro in registros if registro["categoria"] == categoria]
        nacional = promedio_por_fecha(de_categoria)
        tattersall = historia_operador(de_categoria, "tattersall")
        fegosa = historia_operador(de_categoria, "fegosa")
        categorias[categoria] = {"nacional": nacional, "tattersall": tattersall, "fegosa": fegosa, "ultimo_nacional": ultimo(nacional), "ultimo_tattersall": ultimo(tattersall), "ultimo_fegosa": ultimo(fegosa)}
    ultima_fecha = max(str(registro["fecha"]) for registro in registros)
    return {"fuente": "ODEPA / Asociación Gremial de Ferias Ganaderas de Chile (AFECH)", "metodo": "Precio promedio por kilo de los 5 primeros precios según feria, nominal sin IVA. KleoGuard calcula un promedio simple de las ferias publicadas por jornada.", "actualizado_en_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "ultima_jornada_publicada": ultima_fecha, "boletines_consultados": fuentes, "advertencias": errores, "categorias": categorias}


if __name__ == "__main__":
    resultado = construir()
    DESTINO.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Mercado actualizado: {resultado['ultima_jornada_publicada']} · {len(resultado['boletines_consultados'])} boletines")
