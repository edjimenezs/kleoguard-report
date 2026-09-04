#!/usr/bin/env python3
"""Genera una referencia semanal experimental para novillos y vaquillas.

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
DESTINO_VALIDACION = RAIZ / "market-validation-2026.json"
CATEGORIAS = (
    "Novillo Gordo",
    "Novillo Engorda",
    "Vaquilla Gorda",
    "Vaquilla Engorda",
)
SEMANAS_FUTURAS = 4
INICIO_ENTRENAMIENTO_VALIDACION = date(2024, 1, 1)
FIN_ENTRENAMIENTO_VALIDACION = date(2025, 12, 31)
ANIO_VALIDACION = 2026


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


def pronosticar(
    serie: list[tuple[date, float]], semanas_futuras: int
) -> tuple[list[dict[str, object]], float]:
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

    siguiente = semana(fechas[-1]) + timedelta(days=7)
    filas_futuras: list[dict[str, object]] = []
    historial_extendido = list(valores)

    for _ in range(semanas_futuras):
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

    return filas_futuras, amplitud


def proyeccion(serie: list[tuple[date, float]]) -> dict[str, object]:
    filas_futuras, amplitud = pronosticar(serie, SEMANAS_FUTURAS)
    fechas = [fila[0] for fila in serie]
    valores = [fila[1] for fila in serie]

    return {
        "corte_historia": fechas[-1].isoformat(),
        "filas_historia": len(serie),
        "modelo": "Referencia experimental: último precio, tendencia de 4 semanas y estacionalidad semanal.",
        "variacion_referencia_pct": round(amplitud * 100, 1),
        "ultimo_observado": round(valores[-1]),
        "pronosticos": filas_futuras,
    }


def validacion_2026(serie: list[tuple[date, float]]) -> dict[str, object]:
    """Simula 2026 con información disponible sólo hasta el 31-12-2025."""
    entrenamiento = [
        fila
        for fila in serie
        if INICIO_ENTRENAMIENTO_VALIDACION <= fila[0] <= FIN_ENTRENAMIENTO_VALIDACION
    ]
    observados = {fecha: valor for fecha, valor in serie if fecha.year == ANIO_VALIDACION}
    if len(entrenamiento) < 12:
        raise RuntimeError("La validación 2026 requiere al menos 12 semanas de 2024-2025.")

    pronosticos, amplitud = pronosticar(entrenamiento, 52)
    comparables = [
        (fila, observados[date.fromisoformat(str(fila["fecha"]))])
        for fila in pronosticos
        if date.fromisoformat(str(fila["fecha"])) in observados
    ]
    errores = [abs(float(fila["estimado"]) - observado) for fila, observado in comparables]
    errores_pct = [error / observado for error, (_, observado) in zip(errores, comparables) if observado]
    dentro_rango = [
        float(fila["minimo"]) <= observado <= float(fila["maximo"])
        for fila, observado in comparables
    ]
    filas = []
    for fila in pronosticos:
        fecha = date.fromisoformat(str(fila["fecha"]))
        observado = observados.get(fecha)
        filas.append({**fila, "observado": round(observado) if observado is not None else None})

    return {
        "inicio_entrenamiento": INICIO_ENTRENAMIENTO_VALIDACION.isoformat(),
        "corte_entrenamiento": entrenamiento[-1][0].isoformat(),
        "fin_proyeccion": pronosticos[-1]["fecha"],
        "filas_entrenamiento": len(entrenamiento),
        "modelo": "60 % último precio, 25 % promedio de 4 semanas y 15 % estacionalidad semanal.",
        "variacion_referencia_pct": round(amplitud * 100, 1),
        "semanas_con_observado": len(comparables),
        "error_abs_medio": round(mean(errores)) if errores else None,
        "error_pct_abs_medio": round(mean(errores_pct) * 100, 1) if errores_pct else None,
        "cobertura_rango_pct": round(mean(dentro_rango) * 100, 1) if dentro_rango else None,
        "proyeccion_y_observado": filas,
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


def construir_validacion() -> dict[str, object]:
    mercado = cargar_json(ORIGEN)
    categorias_origen = mercado.get("categorias", {})
    if not isinstance(categorias_origen, dict):
        raise RuntimeError("market-data.json no tiene categorías.")

    categorias: dict[str, object] = {}
    for categoria in CATEGORIAS:
        bloque = categorias_origen.get(categoria, {})
        filas = bloque.get("nacional", []) if isinstance(bloque, dict) else []
        categorias[categoria] = validacion_2026(valores_semanales(filas))

    return {
        "fuente_historia": "ODEPA / AFECH, precios públicos chilenos observados.",
        "alcance": (
            "Validación histórica fuera de muestra: la proyección de todo 2026 se "
            "calcula usando exclusivamente jornadas de 2024 y 2025. Los valores 2026 "
            "se muestran después sólo para comparar; no entran al cálculo."
        ),
        "estado": "validacion_historica",
        "categorias": categorias,
    }


def comparable(contenido: dict[str, object]) -> str:
    return json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    resultado = construir()
    validacion = construir_validacion()
    actual = cargar_json(DESTINO) if DESTINO.exists() else {}
    actual_validacion = cargar_json(DESTINO_VALIDACION) if DESTINO_VALIDACION.exists() else {}
    if comparable(actual) == comparable(resultado):
        print("Pronóstico sin cambios.")
    else:
        DESTINO.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Pronóstico experimental recalculado.")
    if comparable(actual_validacion) == comparable(validacion):
        print("Validación histórica sin cambios.")
    else:
        DESTINO_VALIDACION.write_text(
            json.dumps(validacion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("Validación histórica 2026 recalculada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
