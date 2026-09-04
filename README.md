# KleoGuard · Reporte familiar

Página estática de indicadores comerciales agregados para compartir por GitHub Pages.

No contiene correos, archivos adjuntos, RUT, DIIO ni documentos individuales.

## Vistas públicas

- **Trazabilidad:** indicadores comerciales agregados, sin exponer documentos ni datos personales.
- **Mercado:** precios públicos observados de ganado. La vista está enlazada desde la portada para que se pueda alternar sin compartir otra URL.

## Datos de mercado

`market-data.json` es una caché generada a partir de datos públicos de ODEPA/AFECH. Contiene precios por categoría, feria y fecha; no incorpora información de correos, SII, SAG ni del productor.

`market-forecast.json` contiene la referencia futura de cuatro semanas. `market-validation-2026.json` documenta una prueba fuera de muestra: proyecta todo 2026 usando únicamente precios semanales de 2024 y 2025 y luego compara esa proyección con las jornadas 2026 efectivamente publicadas. También entrega agregados mensuales de esa prueba y un escenario mensual experimental hasta 2028. Los valores observados de 2026 no se usan en el cálculo.

Para actualizarla localmente:

```bash
python scripts/actualizar_mercado_odepa.py
```

La fuente publica información por jornada o semana; por eso la última fecha disponible puede ser anterior al día calendario. Antes de publicar una actualización hay que revisar el `git diff`, verificar que la fecha y los valores sean coherentes y evitar publicar cambios que sólo modifiquen advertencias técnicas o metadatos.
