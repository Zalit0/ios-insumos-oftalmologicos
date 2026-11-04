# Contexto de IOS — estado al 29/10/2026

Este archivo resume qué se hizo, cómo está armado y qué queda pendiente.
La fuente de verdad de las reglas de negocio sigue siendo [PLAN.md](PLAN.md)
(ya actualizado con los ajustes de v1.1); esto es un resumen de avance, no
la especificación.

## Qué es IOS

App de escritorio (Windows, PySide6) que reemplaza la planilla de Excel de
cuentas corrientes y caja de la distribuidora de cristales oftálmicos. Las
10 etapas del plan original están completas, y también las 7 etapas de
ajustes post-lanzamiento de [AJUSTES_V1.1.md](AJUSTES_V1.1.md).

## Cómo está armado

```
ios/
  domain/     cálculos puros (descuento, IVA, saldos, totales, texto), sin DB ni UI
  data/       esquema SQLite, migraciones (PRAGMA user_version, 4 aplicadas), consultas
  services/   casos de uso: valida reglas de negocio, usa domain/ y data/
  reports/    PDF (ReportLab) y Excel (openpyxl)
  ui/         ventana principal (menú superior) + pantallas PySide6, sin lógica propia
  recursos.py resuelve la ruta de assets/ (dev y empaquetado)
tests/        264 pruebas (pytest), incluidas de humo y funcionales de UI
main.py       punto de entrada
instalador/   script de Inno Setup (ios_setup.iss)
docs/         PLAN.md, AJUSTES_V1.1.md, este archivo, MARZO 2024.xlsx (planilla real),
              y manual/ (script que genera el Manual del usuario en PDF)
```

La base vive en `C:\ProgramData\IOS\ios.db` (o en `IOS_DB_PATH` si está
definida, para desarrollo/pruebas). Los montos se guardan como texto exacto
(nunca float) para no perder precisión.

## v1.0 — qué se hizo, etapa por etapa

1. **Base del proyecto**: estructura, esquema SQLite completo, migraciones,
   `domain/calculos.py`.
2. **Clientes y sucursales**: alta, edición, baja lógica, sucursales.
3. **Comprobantes**: carga con descuento e IVA editables, cálculo de final
   e IVA discriminado, anulación, tipos configurables.
4. **Cobranzas, recibos y cheques**: un pago con varias formas de pago
   aplicado a varios remitos, pagos parciales, saldo a favor, anulación
   con contramovimiento de caja.
5. **Cuenta corriente**: estado de cuenta por sucursal y consolidado.
6. **Compras y proveedores**: alta de proveedores, pagos con egreso de
   caja (se puede pagar con un cheque en cartera).
7. **Caja diaria**: abrir/cerrar caja por forma de pago, cierre con saldo
   teórico y arqueo, historial de cierres.
8. **Resumen mensual y dashboard**: réplica de la hoja TOTALES; Inicio
   con deuda total, venta/cobranza vs. mes anterior, total disponible.
9. **Importación desde Excel**: lee `MARZO 2024.xlsx` real, vista previa
   con anomalías, todo en una transacción atómica.
10. **Reportes y empaquetado**: PDF/Excel de los reportes del plan; `.exe`
    con PyInstaller e instalador con Inno Setup.

## v1.1 — ajustes post-lanzamiento, etapa por etapa

Pedidos tras las primeras pruebas reales de la app ([AJUSTES_V1.1.md](AJUSTES_V1.1.md)).

1. **Menú superior**: reemplaza el menú lateral (`QMenuBar`, con atajos
   F2–F5). Pantalla "Acerca de IOS". `reiniciar()`/`actualizar()` como
   convención de toda pantalla al entrar/salir.
2. **Facturación y remitos repetidos**: pantalla nueva de carga rápida
   pensada para teclado (buscador con autocompletado, Enter encadena
   campos). Se saca la restricción de número único: coincide con el mismo
   cliente → pide confirmar; con otro cliente → solo avisa (D1).
   Comprobantes pasa a ser pantalla de consulta, con filtro por fechas.
3. **Cobranzas y apertura de caja**: resumen en vivo (seleccionado,
   cargado, diferencia) en Cobranzas; diálogo de apertura de caja que
   propone el saldo del último cierre y deja corregirlo con nota.
4. **Clientes**: pantalla rediseñada (buscador, filtro de estado, diálogo
   con pestañas Datos/Sucursales). Nombre no repetido (bloqueante), CUIT
   con dígito verificador (aviso), sucursal desactivable salvo la última.
5. **Compras — IVA automático**: el monto cargado es el total con IVA
   incluido; el IVA se calcula solo (misma fórmula que remitos) con la
   tasa elegida (21/10,5/0%), corregible a mano (queda "IVA manual").
6. **Reportes nuevos y gráficos**: "Compras por cliente" (detalle o
   ranking), "Gastos de caja chica" (por categoría), y una pestaña
   "Gráficos" en Resumen mensual con 5 gráficos (QtCharts): venta vs.
   cobranza, deuda total, top 10 clientes, IVA venta vs. compra y
   egresos por categoría, todos a 12 meses salvo el top de clientes.
7. **Importación — resolución de conflictos**: cada anomalía que admite
   una decisión (remito repetido, IVA que no coincide, pago suelto,
   recibo compartido entre hojas, recibo con texto, hoja que parece
   sucursal de otra) se muestra como conflicto con una acción sugerida
   editable, filtro por tipo, "aplicar la sugerida a todos los de este
   tipo", y un resumen final exportable a Excel.

## Bugs reales encontrados y corregidos en el camino

- **Afinidad de columnas DECIMAL** (v1.0, etapa 1→4): declarar los montos
  como tipo `DECIMAL` le daba afinidad NUMERIC a SQLite, que los guardaba
  como `REAL` (float). Se renombró a `DECIMAL_TEXT` (fuerza afinidad TEXT).
- **Aplicar un recibo a un remito de otro cliente** (v1.0, etapa 5): no se
  validaba que el remito fuera del mismo cliente del recibo. Corregido.
- **Recibo compartido entre dos clientes al importar** (v1.0, etapa 9,
  descubierto con el archivo real): `recibos.numero` es único en toda la
  base, no por cliente; si el Excel repite un número de recibo entre dos
  hojas, el segundo se renumera automáticamente (y en v1.1 se puede
  unificar en un recibo si ambas hojas terminan siendo del mismo cliente).
- **Rutas de `assets/` empaquetadas** (v1.0, etapa 10): PyInstaller 6.x
  copia los datos agregados a una subcarpeta `_internal`, no al lado del
  `.exe`. Se centralizó la resolución en `ios/recursos.py` usando
  `sys._MEIPASS`.
- Un par de glitches de renderizado de Qt (widgets "fantasma" en tablas
  con celdas embebidas) resueltos cambiando esas secciones a pestañas o
  filas simples en vez de `QTableWidget` con `setCellWidget`.

## Qué queda pendiente

- **Probar la app de verdad**: instalarla (o correr `dist/IOS/IOS.exe`
  directo) y cargar un mes en paralelo con el Excel real, para confirmar
  que los totales y la caja coinciden. Trabajo manual del usuario.
- **Nada del plan (v1.0 ni los ajustes v1.1) quedó sin construir.** Lo que
  sigue es ajustar lo que surja de usar la app real:
  - Revisión de la usuaria sobre la UI (flujos, textos, atajos).
  - La detección de "hoja que parece sucursal de otra" (etapa 7 de
    AJUSTES_V1.1.md) usa un heurístico simple de prefijo de nombre; puede
    necesitar ajuste si aparecen casos reales que no cubre bien.
  - Si se encuentran diferencias entre los totales de IOS y los del Excel
    al correr en paralelo, hay que explicarlas o corregir el código.
- **Backups**: explícitamente fuera de alcance de esta versión.

## Cómo seguir trabajando

- Pruebas: `pytest` desde la raíz del proyecto (venv en `.venv/`).
- Reconstruir el `.exe`: ver sección "Empaquetado" del
  [README.md](../README.md).
- Si se agregan tablas o columnas nuevas, van en una migración nueva
  (`ios/data/migraciones.py`), nunca modificando las ya aplicadas. Van 4
  migraciones aplicadas (esquema base, `sucursales.activo`,
  `compras.tasa_iva`/`iva_manual`, `recibos.referencia`).
- Manual del usuario (`docs/Manual del usuario IOS.pdf`): se genera con
  `docs/manual/generar_manual.py` (no es parte de la app). Las capturas de
  pantalla van en `docs/manual/capturas/` (ver el `README.md` de esa
  carpeta para la lista de archivos esperados). Cada vez que cambie algo
  de lo que el manual explica, actualizar el contenido del script y
  volver a correrlo:
  ```
  .venv\Scripts\python.exe docs\manual\generar_manual.py
  ```
