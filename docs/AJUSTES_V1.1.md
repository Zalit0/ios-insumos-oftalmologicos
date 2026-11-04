# IOS — Plan de ajustes v1.1

Ajustes surgidos de las primeras pruebas reales de la app. Complementa a
`docs/PLAN.md` (que sigue siendo la fuente de verdad para todo lo que este
archivo no cambia) y parte del estado descrito en `docs/CONTEXTO.md`.

Reglas generales:

- Se trabaja por etapas, en el orden de este archivo. Al terminar cada etapa:
  pruebas en verde, resumen de cambios y frenar hasta recibir OK.
- Columnas o tablas nuevas van en migraciones nuevas
  (`ios/data/migraciones.py`), nunca modificando las ya aplicadas.
- La lógica va en `domain/` y `services/`; la UI no calcula.
- Todo lo nuevo lleva pruebas (`pytest`), incluidas de UI donde ya existan.
- Al terminar todas las etapas: actualizar `docs/PLAN.md` y `docs/CONTEXTO.md`.

## Decisiones tomadas en este plan (a confirmar por el usuario)

Donde el pedido dejaba una opción abierta, se eligió lo siguiente. Si alguna no
es correcta, se corrige antes de la etapa que la usa.

| # | Tema | Decisión | Etapa |
| --- | --- | --- | --- |
| D1 | Remitos con número repetido | Se permiten siempre. Si coincide tipo + número + **mismo cliente**, avisa y pide confirmar (probable doble carga). Si es de **otro cliente**, solo muestra un aviso informativo, sin bloquear | 2 |
| D2 | Monto de una factura de compra | El monto cargado es el total **con IVA incluido**, igual que en los remitos. El IVA se calcula solo y se puede corregir a mano | 5 |
| D3 | Tasa de IVA en compras | Por defecto la de configuración (21%), con opción de 10,5% y 0% por factura | 5 |
| D4 | "Caja chica" | Son los egresos manuales de la caja (gastos y retiros), por categoría | 6 |
| D5 | Gráficos | En pantalla, con QtCharts (ya incluido en PySide6, sin dependencias nuevas). No se agregan al PDF en esta versión | 6 |
| D6 | Pantalla Comprobantes | Queda como pantalla de **consulta** (buscar, filtrar, editar, anular). La carga pasa a la nueva pantalla Facturación | 2 |

## Etapa 1 — Menú superior desplegable

Reemplazar el menú lateral por una barra de menú superior (`QMenuBar`). El área
central sigue siendo un `QStackedWidget` con las pantallas.

| Menú | Opciones |
| --- | --- |
| Inicio | Dashboard |
| Ventas | Facturación, Comprobantes, Cobranzas, Cuenta corriente, Clientes |
| Compras | Compras y proveedores, Pagos a proveedores |
| Caja | Caja diaria, Cheques, Gastos de caja chica |
| Reportes | Resumen mensual, Compras por cliente, Deudores, IVA del mes, Flujo de caja, Exportación para el contador |
| Herramientas | Importar desde Excel, Configuración |
| Ayuda | Acerca de IOS (logo, versión) |

- Atajos de teclado: F2 Facturación, F3 Cobranzas, F4 Caja diaria, F5 Cuenta
  corriente. Se muestran al lado de cada opción.
- El título de la ventana indica la pantalla activa ("IOS — Facturación").
- Las opciones de pantallas que se crean en etapas posteriores (Facturación,
  Gastos de caja chica, Compras por cliente) se agregan al menú en su etapa.
- Toda pantalla expone un método `reiniciar()` que la deja en blanco; la
  ventana principal lo llama al salir de ella (lo usa Facturación, etapa 2).

**Listo cuando:** se navega a todas las pantallas existentes desde el menú y
con los atajos, y no queda rastro del menú lateral.

## Etapa 2 — Facturación, filtro por fechas y remitos repetidos

### 2.1 Pantalla Facturación (nueva)

Pantalla de carga rápida de comprobantes, pensada para usarse con teclado.

1. **Buscador de óptica** arriba: campo con autocompletado (`QCompleter`) que
   busca por cualquier parte del nombre, sin distinguir mayúsculas ni acentos
   ("optica" encuentra "ÓPTICA CIUDAD"). Solo clientes activos.
2. Al elegir el cliente: si tiene más de una sucursal aparece el selector de
   sucursal; si es Particulares, aparece el campo de nombre del particular.
   Se muestran el descuento e IVA por defecto del cliente y su saldo actual.
3. **Formulario:** tipo (RTO por defecto), número, fecha (hoy por defecto; en
   la sesión recuerda la última usada), monto de lista, descuento (el del
   cliente, editable), IVA SÍ/NO (el del cliente, editable). Muestra en vivo
   monto final e IVA discriminado.
4. Enter avanza de campo; Enter en el último campo guarda. Después de guardar,
   el formulario se limpia (mantiene cliente, sucursal, tipo y fecha) y el foco
   vuelve a "número".
5. **Debajo:** tabla "Cargados en esta sesión" con los comprobantes recién
   guardados (número, fecha, sucursal, lista, descuento, final, IVA) y el
   total de la sesión.
   - Doble clic o botón Editar carga el comprobante en el formulario para
     corregirlo; Guardar actualiza esa fila en lugar de crear otra.
   - Si el comprobante ya tiene pagos aplicados, no se pueden cambiar monto,
     descuento ni IVA (se ofrece anularlo). Sí se pueden corregir número y fecha.
   - Botón Anular, con confirmación.
6. **Reinicio:** al cambiar de cliente, la tabla de la sesión y el formulario
   quedan en blanco. Al salir de la pantalla (cambio de menú o cierre), todo
   queda en blanco; al volver, se empieza de cero. Los datos ya están
   guardados en la base: lo que se borra es solo la vista de la sesión.

### 2.2 Remitos con número repetido (D1)

- Quitar cualquier restricción de unicidad sobre tipo + número (si existe un
  índice `UNIQUE`, se elimina en una migración nueva).
- Al guardar, buscar coincidencias de tipo + número:
  - **Mismo cliente:** diálogo "Ya existe el RTO 45126 de este cliente, del
    05/03/2024 por $21.608. ¿Guardar igual?". Muestra fecha y monto para
    distinguir.
  - **Otro cliente:** aviso no bloqueante bajo el formulario ("El número 45142
    también está cargado en MIRAGE").
- En todas las listas y PDF, los comprobantes se identifican por número +
  fecha + cliente, nunca solo por número. Revisar búsquedas y la importación
  para que no asuman número único.
- Dejar el modelo preparado para que en el futuro IOS genere los remitos
  numerados (no implementarlo ahora).

### 2.3 Comprobantes: filtro entre fechas (D6)

- La pantalla Comprobantes queda de consulta. Filtros: **desde / hasta**
  (con atajos "Este mes", "Mes anterior", "Este año"), cliente (mismo
  buscador con autocompletado), tipo, número y estado.
- Pie de la tabla con cantidad y totales (lista, final, IVA) de lo filtrado.
- Editar y anular siguen funcionando como hoy. Quitar el formulario de carga
  de esta pantalla.

**Listo cuando:** se cargan 10 remitos de un cliente solo con teclado, se
corrige uno desde la tabla de la sesión, al cambiar de cliente o de pantalla
todo queda en blanco, y dos remitos con el mismo número en clientes distintos
se guardan sin bloquear.

## Etapa 3 — Cobranzas y apertura de caja

### 3.1 Cobranzas: suma de lo seleccionado

Mientras se tildan remitos, mostrar siempre visible:

| Concepto | Ejemplo |
| --- | --- |
| Remitos seleccionados | 3 — $45.320,00 |
| Formas de pago cargadas | $50.000,00 |
| Diferencia | Falta $X / Excedente $Y (queda como saldo a favor) |

Se actualiza en cada tilde y en cada cambio de monto. Botón "Seleccionar
todos" y opción de completar el monto del pago con el total seleccionado.

### 3.2 Abrir caja

Hoy la apertura no muestra el saldo inicial ni deja corregirlo. Al abrir la
caja, un diálogo muestra una fila por forma de pago:

| Forma de pago | Saldo del último cierre | Saldo inicial (editable) |
| --- | --- | --- |
| Efectivo | $120.500,00 | $120.500,00 |

- El primer día, el último cierre es 0.
- Si se modifica algún saldo, la nota es obligatoria y la diferencia queda como
  movimiento de ajuste (ya definido en PLAN.md, sección Caja diaria).
- Botones Abrir caja / Cancelar.

**Listo cuando:** una cobranza muestra la suma correcta al tildar y destildar,
y abrir la caja muestra el saldo del cierre anterior, permite corregirlo y
registra el ajuste con nota.

## Etapa 4 — Clientes

Rediseño para que alta y edición sean directas:

- **Lista** con buscador (nombre, CUIT, localidad), columnas nombre, localidad,
  teléfono, saldo, y un filtro Activos / Dados de baja / Todos.
- Botones **Nuevo**, **Editar** (o doble clic) y **Dar de baja / Reactivar**.
- **Ficha en un diálogo** con dos pestañas:
  - Datos: nombre (único campo obligatorio), CUIT, teléfono, dirección,
    localidad, descuento por defecto, IVA por defecto.
  - Sucursales: lista con agregar / renombrar / desactivar. La sucursal
    principal se crea sola y no se puede borrar.
- Validación al lado de cada campo: CUIT con formato y dígito verificador
  (aviso, no bloqueo), descuento entre 0 y 100, nombre no repetido.
- Guardar con Enter, cancelar con Escape. Al guardar, la lista se actualiza y
  queda seleccionado el cliente.

Antes de programar, describir en el resumen de la etapa qué partes del flujo
actual se cambian, para que el usuario lo valide.

**Listo cuando:** dar de alta un cliente con dos sucursales y luego modificar
su descuento lleva pocos pasos y no requiere salir de la pantalla.

## Etapa 5 — Compras: IVA automático (D2, D3)

- Al cargar una factura de proveedor: monto total (con IVA), tasa de IVA
  (21% por defecto, 10,5% o 0%), IVA calculado solo con la misma fórmula que
  los remitos: total × tasa / (100 + tasa), con el redondeo configurado.
- El IVA calculado se puede corregir a mano (por diferencias de redondeo del
  proveedor); si se corrige, se marca como "IVA manual".
- Migración: agregar a `compras` la tasa de IVA y la marca de IVA manual. Las
  compras ya cargadas quedan con su IVA actual marcado como manual.
- La lógica va en `domain/calculos.py`, reutilizando la del IVA de remitos.

**Listo cuando:** una factura de $121.000 al 21% muestra IVA $21.000 sin
tocar nada, y una al 10,5% calcula bien.

## Etapa 6 — Reportes nuevos y gráficos

### 6.1 Compras por cliente (nuevo)

Responde "¿cuánto compró este cliente entre tal y tal fecha?".

- Filtros: cliente (buscador), desde / hasta, sucursal (todas o una).
- Resultado: lista de comprobantes del período y totales de lista, descuento,
  final, IVA, cobrado y pendiente. Si hay sucursales, subtotal por sucursal.
- Opción "Todos los clientes" que muestra un ranking del período (cliente,
  cantidad de comprobantes, total final), ordenado de mayor a menor.
- Exportar a PDF y Excel.

### 6.2 Gastos de caja chica (D4)

- Filtros: desde / hasta, categoría (todas o una), forma de pago.
- Lista de egresos manuales (fecha, categoría, concepto, forma de pago, monto)
  y subtotal por categoría.
- Exportar a PDF y Excel.

### 6.3 Gráficos en el Resumen mensual (D5)

Agregar una pestaña "Gráficos" al Resumen mensual:

1. Venta vs. cobranza de los últimos 12 meses (barras agrupadas).
2. Deuda total de clientes al cierre de cada mes, últimos 12 meses (línea).
3. Top 10 clientes por venta del mes (barras horizontales).
4. IVA venta vs. IVA compra de los últimos 12 meses (barras agrupadas).
5. Egresos de caja del mes por categoría (barras horizontales).

- Los datos de cada gráfico salen de funciones en `services/` con pruebas;
  los gráficos solo dibujan.
- Montos con formato argentino ($ 1.234,56), ejes con título, sin gráficos de
  torta.

**Listo cuando:** los tres reportes muestran datos correctos contra casos de
prueba y los gráficos coinciden con las cifras del resumen.

## Etapa 7 — Importación: resolución de conflictos

Hoy la vista previa muestra las anomalías, pero no deja decidir qué hacer con
cada una. Agregar una acción por conflicto, con una opción sugerida:

| Conflicto | Acciones posibles | Sugerida |
| --- | --- | --- |
| Remito repetido | Importar ambos / Omitir este | Importar ambos (D1) |
| IVA que no coincide | Usar IVA recalculado / Conservar el del Excel | Recalculado |
| Pago suelto sin remito | Registrar como saldo a favor / Omitir | Saldo a favor |
| Recibo compartido entre hojas | Renumerar el segundo / Unificar en un recibo | Renumerar |
| Recibo con texto (TRANSF, S/R, S/N) | Número automático y el texto como referencia / Omitir el pago | Número automático |
| Hoja que parece sucursal de otro cliente | Importar como sucursal de… / Como cliente nuevo | Según nombre parecido |

- Cada conflicto se ve en una fila con su detalle (hoja, fila del Excel,
  valores) y un selector de acción.
- Botones "Aplicar la sugerida a todos los de este tipo" y filtro por tipo.
- El botón Importar se habilita solo cuando no queda ningún conflicto sin
  decidir. La importación sigue siendo una sola transacción.
- Al terminar, un resumen de qué se hizo con cada conflicto, exportable a
  Excel.

**Listo cuando:** `MARZO 2024.xlsx` se importa resolviendo cada conflicto a
mano, y el resultado coincide con la decisión tomada en cada caso.

## Fuera de alcance de esta versión

- Generación automática de remitos numerados por IOS (próxima versión; la
  etapa 2 deja el modelo preparado).
- Gráficos dentro de los PDF.
- Copias de seguridad.
