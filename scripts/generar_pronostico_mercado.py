#!/usr/bin/env python3
"""Genera una referencia semanal experimental para Novillo Gordo y Engorda.

No es un precio de compra/venta ni reemplaza la feria. El cálculo usa solamente
precios chilenos publicados antes de cada semana futura:

* 60 % última semana observada;
* 25 % promedio de las últimas cuatro semanas;
* 15 % promedio de la misma semana del año, cuando existe.

Es una referencia simple y explicable. El rango no es una garantía: representa
la variación reciente observada en la serie pública.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from statistics import mean


RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "market-data.json"
DESTINO = RAIZ / "market-forecast.json"
CATEGORIAS = ("Novillo Gordo", "Novillo Engorda")
SEMANAS_FUTURAS = 4


def semana(fecha: date) -> date:
    """Lunes de la semana ISO de una fecha."""
    return fecha - timedelta(days=fecha.weekday())


def cargar_json(ruta: Path) -> dict[str, object]:
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(contenido, dict):
        raise RuntimeError(f"{ruta.name} no contiene un objeto JSON.")
    return contenido


def valores_semanales(filas: object) -> list[tuple[date, float]]:
    por_semana: dict[date, list[float]] = {}
    for fila in filas if isinstance(filas, list) else []:
        if not isinstance(fila, dict):
            continue
        try:
            fecha = date.fromisoformat(str(fila["fecha"]))
            valor = float(fila["valor"])
        except (KeyError, TypeError, ValueError):
            continue
        if valor <= 0:
            continue
        por_semana.setdefault(semana(fecha), []).append(valor)
    return [(fecha, mean(valores)) for fecha, valores in sorted(por_semana.items())]


def percentil(valores: list[float], nivel: float) -> float:
    if not valores:
        return 0.08
    ordenados = sorted(valores)
    posicion = (len(ordenados) - 1) * nivel
    inferior = int(posicion)
    superior = min(inferior + 1, len(ordenados) - 1)
    fraccion = posicion - inferior
    return ordenados[inferior] + (ordenados[superior] - ordenados[inferior]) * fraccion


def proyeccion(serie: list[tuple[date, float]]) -> dict[str, object]:
    if len(serie) < 12:
        raise RuntimeError("Se requieren al menos 12 semanas públicas para generar una referencia.")

    fechas = [fila[0] for fila in serie]
    valores = [fila[1] for fila in serie]
    por_semana_ano: dict[int, list[float]] = {}
    for fecha, valor in serie:
        por_semana_ano.setdefault(fecha.isocalendar().week, []).append(valor)

    cambios_relativos = [
        abs(valor / anterior - 1)
        for anterior, valor in zip(valores, valores[1:])
        if anterior > 0
    ]
    amplitud = max(0.035, min(percentil(cambios_relativos, 0.80), 0.22))

    recientes = list(valores[-4:])
    ultimo = valores[-1]
    siguiente = semana(fechas[-1]) + timedelta(days=7)
    filas_futuras: list[dict[str, object]] = []
    historial_extendido = list(valores)

    for _ in range(SEMANAS_FUTURAS):
        estacional = por_semana_ano.get(siguiente.isocalendar().week)
        promedio_estacional = mean(estacional) if estacional else mean(historial_extendido[-13:])
        estimado = 0.60 * historial_extendido[-1] + 0.25 * mean(historial_extendido[-4:]) + 0.15 * promedio_estacional
        estimado = round(estimado)
        filas_futuras.append(
            {
                "fecha": siguiente.isoformat(),
                "estimado": estimado,
                "minimo": round(estimado * (1 - amplitud)),
                "maximo": round(estimado * (1 + amplitud)),
            }
        )
        historial_extendido.append(estimado)
        siguiente += timedelta(days=7)

    return {
        "corte_historia": fechas[-1].isoformat(),
        "filas_historia": len(serie),
        "modelo": "Referencia experimental: último precio, tendencia de 4 semanas y estacionalidad semanal.",
        "variacion_referencia_pct": round(amplitud * 100, 1),
        "ultimo_observado": round(ultimo),
        "pronosticos": filas_futuras,
    }


def construir() -> dict[str, object]:
    mercado = cargar_json(ORIGEN)
    categorias_origen = mercado.get("categorias", {})
    if not isinstance(categorias_origen, dict):
        raise RuntimeError("market-data.json no tiene categorías.")

    categorias: dict[str, object] = {}
    for categoria in CATEGORIAS:
        bloque = categorias_origen.get(categoria, {})
        filas = bloque.get("nacional", []) if isinstance(bloque, dict) else []
        categorias[categoria] = proyeccion(valores_semanales(filas))

    return {
        "fuente_historia": "ODEPA / AFECH, precios públicos chilenos observados.",
        "alcance": (
            "Referencia experimental de cuatro semanas. Usa sólo precios públicos "
            "chilenos publicados hasta la última jornada; no incorpora datos privados "
            "ni señales externas todavía."
        ),
        "estado": "experimental",
        "categorias": categorias,
    }


def comparable(contenido: dict[str, object]) -> str:
    return json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    resultado = construir()
    actual = cargar_json(DESTINO) if DESTINO.exists() else {}
    if comparable(actual) == comparable(resultado):
        print("Pronóstico sin cambios.")
        return 0
    DESTINO.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Pronóstico experimental recalculado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
