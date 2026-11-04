# Plan: IOS (Insumos Oftalmológicos Santiago) – cuentas corrientes y caja

Oct 28, 2026 · @Gonzalo

> **Nota (v1.1):** este documento fue actualizado para reflejar los ajustes
> de `docs/AJUSTES_V1.1.md` (menú superior, pantalla Facturación, remitos
> repetidos permitidos, pantalla Clientes rediseñada, IVA automático en
> compras, nuevos reportes y gráficos, resolución de conflictos al
> importar), ya mergeados acá. `AJUSTES_V1.1.md` queda como historial de
> esa ronda de cambios, no como una segunda fuente de verdad.

## Objetivo y alcance

IOS (Insumos Oftalmológicos Santiago) reemplaza la planilla mensual de Excel por un programa de escritorio para Windows, en una sola PC y con dos usuarios, donde clientes, remitos, cobranzas, compras y caja viven en una base de datos única y sin fórmulas que se rompan.

**Qué resuelve:** hoy cada mes se arma una planilla nueva y cada cliente nuevo exige copiar una hoja. Eso rompe fórmulas (el Excel de marzo ya tiene `#REF!` en ganancia teórica, total disponible, IVA venta e IVA deuda) y se pierde información. En la app el mes es un filtro, los saldos se calculan solos y los clientes se dan de alta con un formulario.

**Dentro del alcance:** clientes y sucursales, comprobantes, cobranzas con recibo numerado, cuenta corriente, compras y pagos a proveedores, cierre de caja diario, resumen mensual, dashboard, estados de cuenta en PDF e importación opcional desde Excel.

**Fuera del alcance (por ahora):** facturación electrónica ARCA, stock, usuarios con contraseña, copias de seguridad automáticas y uso desde varias PC.

## Decisiones ya tomadas

| Tema | Decisión |
| --- | --- |
| Usuarios y equipo | Dos personas, una sola PC con Windows, sin login |
| Interfaz | Ventana de escritorio, no navegador |
| Comprobantes | Remito (`RTO`) por defecto; la lista de tipos es configurable para agregar otros |
| Monto de lista | Lo tipea el usuario en cada comprobante |
| Descuento | Fijo por cliente, pero editable en cada remito (por ejemplo si paga en tiempo) |
| IVA | 21%. Va incluido en el monto final solo si el remito tiene IVA SÍ, y se muestra discriminado en su columna. Cada cliente tiene un valor por defecto y cada remito puede cambiarlo |
| Clientes | Guardan CUIT, teléfono, dirección y localidad. Un cliente puede tener sucursales (caso Croma y Croma Fdez.) con estado de cuenta por sucursal y resumen total. El nombre no se repite (bloqueante); el CUIT se valida (formato + dígito verificador) solo como aviso. Una sucursal se puede desactivar, pero nunca la última activa de un cliente |
| Particulares | Un cliente especial para ventas a consumidores finales |
| Cobranzas | Un pago puede cubrir varios remitos; el sistema genera un recibo numerado |
| Formas de pago | Efectivo, transferencia y cheque; configurable para sumar otras. Un recibo puede combinar varias formas de pago. Los cheques guardan número, cliente, banco, monto y fecha de cobro |
| Comisión | Porcentaje configurable sobre la venta total (en el Excel de marzo es 15%). Es un dato informativo del resumen, no sale de la caja; con 0% queda desactivada |
| Ganancia teórica | Total venta − comisión − compras − (IVA venta − IVA compra) |
| Depósitos | Pagos a proveedores (salen de la caja) |
| Compras | Facturas de proveedores con número y monto total (con IVA incluido); el IVA se calcula solo con la tasa (21% por defecto, 10,5% o 0%) y se puede corregir a mano (queda marcado "IVA manual") |
| IVA deuda | IVA venta − IVA compra |
| Meses | Una sola base continua; el mes es un filtro. Los saldos pasan solos al mes siguiente. Total disponible = saldo de caja, controlado con un cierre de caja diario |
| Dashboard | Sí, con deuda total, saldos por cliente, total disponible y estado de la caja del día |
| Reportes | Estado de cuenta, recibo, cierre y flujo de caja, cheques en cartera, resumen mensual y exportación a Excel |
| Importación | Opcional; se puede empezar desde cero sin datos |
| Copias de seguridad y permisos | No en esta primera versión |

## Modelo de datos

Base SQLite en un solo archivo. Regla central: el saldo nunca se guarda, siempre se calcula a partir de comprobantes y pagos aplicados. Así no hay nada que se desactualice.

| Tabla | Campos principales | Para qué |
| --- | --- | --- |
| `clientes` | nombre, CUIT, teléfono, dirección, localidad, descuento por defecto (%), con IVA por defecto (sí/no), es\_particular, activo | Alta de clientes. El cliente Particulares queda marcado |
| `sucursales` | cliente, nombre, activo | Croma y Croma Fdez. bajo un mismo cliente. Todo cliente tiene al menos una sucursal activa; una sucursal se puede desactivar pero nunca la última |
| `tipos_comprobante` | nombre, abreviatura, activo | Configurable. Viene cargado `RTO` |
| `comprobantes` | tipo, número, fecha, cliente, sucursal, nombre del particular (opcional), monto de lista, descuento (%), monto final, con IVA (sí/no), IVA discriminado, notas, estado (vigente/anulado) | Reemplaza las filas de cada hoja de cliente |
| `formas_pago` | nombre, tipo (efectivo, banco, cheque, otro), activo | Efectivo, Transferencia y Cheque. Configurable. El tipo indica qué datos pedir: si es cheque, pide los datos del cheque |
| `recibos` | número correlativo, fecha, cliente, monto total, origen (manual o importado), referencia (opcional), estado | Se genera al asentar un pago. Lo que no se aplica a remitos queda como saldo a favor del cliente. `referencia` guarda el texto original (TRANSF, S/R, S/N...) cuando un recibo importado no tenía número |
| `recibo_pagos` | recibo, forma de pago, monto, cheque (opcional) | Un recibo puede combinar efectivo, transferencia y varios cheques |
| `cheques` | número, cliente, banco, monto, fecha de cobro, recibo de origen, estado (en cartera, cobrado, entregado a proveedor, rechazado, anulado) | Se crea al cobrar con cheque |
| `aplicaciones_pago` | recibo, comprobante, monto aplicado | Une un recibo con uno o varios remitos, incluso en pagos parciales |
| `proveedores` | nombre, CUIT (opcional) | Lentex, Cristal Depot, etc. |
| `compras` | proveedor, fecha, número de factura, monto (con IVA incluido), IVA, tasa de IVA, IVA manual (sí/no) | Hoja COMPRAS del Excel. El IVA se calcula solo a partir del monto y la tasa; si se corrige a mano, queda marcado |
| `pagos_proveedor` | proveedor, fecha, monto, forma de pago, cheque entregado (opcional), comprobante o referencia | Los "depósitos" del Excel |
| `categorias_caja` | nombre, tipo (ingreso/egreso), activo | Gastos, retiros, aportes. Configurable |
| `movimientos_caja` | fecha y hora, tipo (ingreso/egreso), forma de pago, monto, categoría, concepto, origen (recibo, pago a proveedor, anulación, transferencia interna, ajuste de saldo inicial o manual), movimiento relacionado (opcional), cierre al que pertenece | Todo movimiento de dinero. Los de recibos, pagos a proveedores y anulaciones se generan solos |
| `cierres_caja` | fecha, nota, estado (abierto/cerrado) | Un registro por día |
| `cierres_caja_detalle` | cierre, forma de pago, saldo inicial, ingresos, egresos, saldo teórico, arqueo, diferencia | Una fila por forma de pago, así sirve aunque se agreguen formas nuevas |
| `configuracion` | IVA (21%), comisión (% sobre venta total; 0 la desactiva), número inicial de recibo, redondeo (cantidad de decimales, por defecto 2), otros parámetros | Valores que hoy están tipeados en las fórmulas |

**Dinero:** guardar importes como enteros en centavos o como `Decimal`, nunca como `float`. El Excel de marzo ya arrastra restos de punto flotante (por ejemplo 1654,786115…).

## Reglas de negocio y fórmulas

Todo cálculo vive en un solo módulo con pruebas automáticas. La pantalla muestra resultados, no calcula.

| Concepto | Regla |
| --- | --- |
| Monto final | monto de lista × (1 − descuento / 100). El descuento arranca con el del cliente y se puede cambiar en cada remito. Monto final e IVA se redondean según la configuración |
| IVA del remito | Si el remito va con IVA SÍ: el final ya lo incluye y el IVA discriminado es monto final × tasa / (100 + tasa), con la tasa de configuración (hoy 21%), mostrado en su propia columna. Si va con IVA NO: 0 |
| Saldo del comprobante | monto final − suma de montos aplicados desde recibos |
| Saldo del cliente | Suma de saldos de sus comprobantes vigentes (todas las sucursales) − saldo a favor. Saldo a favor = monto de sus recibos vigentes − montos aplicados. Si el resultado es negativo, el cliente tiene saldo a favor |
| Total venta del mes | Suma del monto final de los comprobantes vigentes con fecha en el mes |
| Total pagos del mes | Suma de los montos aplicados a comprobantes con fecha en el mes, aunque el recibo sea de otro mes |
| Total saldos | Total venta − pagos aplicados a esas ventas |
| IVA venta | Suma del IVA de los comprobantes vigentes del mes |
| IVA compra | Suma del IVA de las compras del mes |
| IVA deuda | IVA venta − IVA compra |
| Comisión | Porcentaje configurable × total venta del mes. Solo se muestra en el resumen y no genera movimiento de caja. Con 0% vale 0 |
| Depósitos | Suma de pagos a proveedores del mes |
| Ganancia teórica | Total venta − comisión − total compras − (IVA venta − IVA compra) |

**Integridad:**

- Los comprobantes y recibos se anulan, no se borran. Un recibo anulado libera los saldos que cubría y sus cheques pasan a estado anulado.
- Tipo + número de comprobante repetido: se permite siempre (no hay índice `UNIQUE`). Si coincide con uno vigente del **mismo cliente**, pide confirmar (probable doble carga); si es de **otro cliente**, solo avisa, sin bloquear. El Excel de marzo tiene el remito 45126 dos veces en La Óptica y el 45142 en Crisol y en Mirage. Los comprobantes se identifican por número + fecha + cliente, nunca solo por número.
- Un recibo no puede aplicar más que el saldo pendiente de cada remito. Si el cliente paga de más, el excedente queda asentado como saldo a favor y se puede aplicar a remitos futuros.
- Los recibos se numeran de forma correlativa y automática, con número inicial configurable. Si el número que toca ya existe (por ejemplo, un recibo importado), usa el inmediato superior libre.
- Agregar un cliente, sucursal, tipo de comprobante o forma de pago no toca ningún dato existente.

**Caja diaria y total disponible:**

Todo movimiento de dinero genera un movimiento de caja: los recibos son ingresos y los pagos a proveedores son egresos. Además se pueden cargar gastos, retiros y aportes manuales.

| Concepto | Regla |
| --- | --- |
| Saldo inicial del día | Se pide al abrir la caja. Propone el arqueo del cierre anterior (0 el primer día) y se puede modificar. Si se modifica, la diferencia queda como movimiento de ajuste con nota obligatoria |
| Saldo teórico | Saldo inicial + ingresos del día − egresos del día |
| Arqueo | Monto verificado al cerrar: efectivo contado, banco contra el extracto y cheques contra la cartera |
| Diferencia | Arqueo − saldo teórico. Si no es cero, se pide una nota |
| Cierre | Congela los movimientos del día y no se reabre |
| Corrección de un día cerrado | Anular un recibo o un pago de un día cerrado genera un contramovimiento en la caja del día actual |
| Transferencia interna | Depositar efectivo en el banco o cobrar un cheque: egreso en una forma de pago e ingreso en otra por el mismo monto. No cambia el total disponible |
| Pago con cheque de terceros | Egreso en la forma cheque; el cheque pasa a "entregado a proveedor" |
| Datos importados | Los recibos importados desde Excel no generan movimientos de caja |
| Total disponible | Saldo del último cierre más los movimientos posteriores |

La caja registra efectivo, transferencias y cheques: cada recibo o pago a proveedor genera su movimiento en la forma de pago elegida. Saldo inicial, saldo teórico, arqueo y diferencia se llevan por separado para cada forma de pago.

## Pantallas

Ventana principal con menú superior desplegable (`Inicio`, `Ventas`, `Compras`,
`Caja`, `Reportes`, `Herramientas`, `Ayuda`). Atajos: F2 Facturación, F3
Cobranzas, F4 Caja diaria, F5 Cuenta corriente. El título de la ventana
indica la pantalla activa. Cada pantalla replica una tarea que hoy se hace
en Excel.

| Pantalla | Qué se hace ahí |
| --- | --- |
| Inicio (dashboard) | Deuda total, venta y cobranza del mes, total disponible, estado de la caja del día, clientes con más saldo, saldos por antigüedad |
| Facturación | Carga rápida de comprobantes pensada para teclado: buscador de cliente con autocompletado, sucursal y nombre de particular si corresponden, formulario con Enter para avanzar de campo y guardar, tabla de lo cargado en la sesión con edición y anulación |
| Comprobantes | Pantalla de **consulta**: filtros por fechas (con atajos Este mes/Mes anterior/Este año), cliente, tipo, número y estado; pie con cantidad y totales. Editar y anular. La carga de remitos pasó a Facturación |
| Cobranzas | Elegir cliente, ver sus remitos pendientes, tildar cuáles cubre el pago e indicar una o varias formas de pago con su monto (si es cheque, pide número, banco, monto y fecha de cobro); un resumen en vivo muestra lo seleccionado, lo cargado y la diferencia. Si el monto supera lo tildado, el excedente queda como saldo a favor. También permite aplicar un saldo a favor existente a remitos pendientes, sin movimiento de caja. Al confirmar genera el recibo numerado y los ingresos de caja, y permite imprimirlo o guardarlo en PDF |
| Cuenta corriente | Movimientos, saldo y saldo a favor de un cliente, agrupados por sucursal, con el total consolidado. Botón para exportar el estado de cuenta en PDF |
| Clientes | Lista con buscador (nombre, CUIT, localidad), columnas nombre/localidad/teléfono/saldo y filtro Activos/Dados de baja/Todos. Alta, edición (en un diálogo con pestañas Datos y Sucursales), baja lógica y reactivación |
| Compras y proveedores | Alta de proveedores, carga de facturas con tasa de IVA seleccionable (el IVA se calcula solo y se puede corregir a mano) y registro de pagos a proveedores, que generan el egreso de caja. Se puede pagar con un cheque en cartera |
| Cheques | Cheques en cartera ordenados por fecha de cobro, con cambio de estado: cobrado (transferencia interna al banco), entregado a proveedor o rechazado |
| Caja diaria | Al abrir, un diálogo propone el saldo del último cierre por forma de pago y deja corregirlo (con nota obligatoria si se corrige). Movimientos del día por forma de pago; carga de gastos, retiros, aportes y transferencias internas; botón de cierre que muestra el saldo teórico, pide el arqueo por forma de pago y registra la diferencia. Historial de cierres |
| Gastos de caja chica | Egresos manuales de caja (gastos y retiros) entre dos fechas, filtrables por categoría y forma de pago, con subtotal por categoría. PDF y Excel |
| Resumen mensual | Reemplaza la hoja TOTALES: ventas, pagos, saldos, IVA, comisión, compras, depósitos, ganancia teórica y total disponible del mes elegido, más una pestaña de gráficos (ver "Reportes y dashboard") |
| Compras por cliente | Cuánto compró un cliente (o todos, en un ranking) entre dos fechas, con subtotal por sucursal. PDF y Excel |
| Configuración | IVA, comisión, tipos de comprobante, formas de pago, categorías de caja y número inicial de recibo |
| Importar desde Excel | Opcional, ver sección de importación |

## Reportes y dashboard

| Reporte | Contenido | Salida |
| --- | --- | --- |
| Estado de cuenta por cliente | Remitos, recibos, saldo por sucursal y saldo a favor, más el resumen total del cliente | PDF |
| Recibo | Número, fecha, cliente, formas de pago con los datos de cada cheque y remitos que cubre | PDF o impresión |
| Cierre de caja | Saldo inicial, ingresos, egresos, saldo teórico, arqueo y diferencia por forma de pago | PDF o impresión |
| Flujo de caja | Ingresos y egresos por día y por categoría en un período, con el saldo acumulado | Pantalla y Excel |
| Cheques en cartera | Cheques por fecha de cobro, con cliente, banco, monto y estado | Pantalla y PDF |
| Listado de deudores | Clientes con saldo, ordenados de mayor a menor, con antigüedad del remito más viejo impago | Pantalla, PDF y Excel |
| Resumen mensual | Equivale a la hoja TOTALES, para cualquier mes, con una pestaña de gráficos (venta vs. cobranza, deuda total, top 10 clientes, IVA venta vs. compra y egresos por categoría, últimos 12 meses) | Pantalla, PDF y Excel |
| Compras por cliente | Comprobantes de un cliente en un período, con subtotal por sucursal; o un ranking de todos los clientes | Pantalla, PDF y Excel |
| Gastos de caja chica | Egresos manuales de caja (gastos y retiros) por categoría | Pantalla, PDF y Excel |
| IVA del mes | IVA venta, IVA compra e IVA deuda, con el detalle de comprobantes | Pantalla y Excel |
| Exportación a Excel | Comprobantes, recibos, compras y movimientos de caja de un período, para el contador | Excel |

El dashboard muestra deuda total, venta y cobranza del mes actual contra el anterior, total disponible, estado de la caja del día, los diez clientes con más saldo y los saldos agrupados por antigüedad.

## Importación opcional desde Excel

Es una función del menú, no un paso obligatorio: la app arranca vacía y se puede usar desde cero. Si la usuaria quiere traer un mes viejo, funciona así:

1. Elegir el archivo `.xlsx` (por ejemplo `MARZO 2024.xlsx`). La app lee los valores guardados, no las fórmulas.
2. Cada hoja de cliente se reconoce por su estructura (fecha, tipo, número, monto, descuento, IVA sí/no, pago, recibo, fecha de pago). Se ignoran `TOTALES`, `COMPRAS` y las hojas `VACIO`.
3. Las hojas sin movimientos no crean clientes. Los clientes nuevos se crean solos con el descuento y el IVA que muestre su columna. En la vista previa se puede asignar una hoja como sucursal de otro cliente (por ejemplo Croma Fdez. dentro de Croma).
4. Se muestra una vista previa con altas, remitos y pagos a importar, y la lista de anomalías detectadas. Nada se guarda hasta confirmar.
5. Cada anomalía que admite una decisión se muestra como un **conflicto**, con una acción sugerida ya preseleccionada; se puede cambiar fila por fila, filtrar por tipo y aplicar la sugerida a todos los de un tipo. El botón Importar se habilita cuando no queda ningún conflicto sin decidir (en la práctica, siempre: cada uno arranca con su sugerida).
6. Al confirmar, la importación se hace en una sola transacción: si algo falla, no queda nada a medias. Al terminar, un resumen de qué se decidió para cada conflicto, exportable a Excel.

**Anomalías que debe avisar** (todas aparecen en el Excel de marzo), con la acción sugerida entre paréntesis cuando admite una decisión:

- Número de remito repetido dentro de una hoja (sugerida: importar ambos) o entre hojas (solo informativo, D1).
- IVA distinto de `final × 21/121` (sugerida: usar el recalculado; en Koral, el remito 45150 tiene IVA 7.502 sobre un final de 6.001,60).
- Pagos sueltos sin remito (sugerida: registrar como saldo a favor; en Crisol hay un pago de 2 que deja un saldo de −2).
- Un mismo recibo repartido entre varios remitos de la misma hoja (Del Pilar, recibo 70011, cubre cinco) — no es un conflicto, se agrupa solo.
- Un mismo número de recibo en más de una hoja (sugerida: renumerar el segundo; si ambas hojas terminan siendo del mismo cliente, se puede unificar en un recibo).
- Recibos con texto en lugar de número (sugerida: número automático, con el texto como referencia; `TRANSF`, `S/R`, `S/N`).
- Una hoja cuyo nombre parece sucursal de otra, por ejemplo "CROMA FDEZ." frente a "CROMA" (sugerida: importarla como esa sucursal; no se aplica si no se confirma a mano).

Los recibos importados conservan su número original, no consumen la numeración automática y no generan movimientos de caja.

## Stack técnico y estructura

| Pieza | Propuesta | Motivo |
| --- | --- | --- |
| Lenguaje | Python 3.12 o superior | Pedido del proyecto |
| Interfaz | PySide6 (Qt) | Tablas, formularios y diálogos de aspecto profesional en Windows. Alternativa más simple: CustomTkinter |
| Base de datos | SQLite, un solo archivo `ios.db` | Viene incluido en Python y se empaqueta con el programa. No hay servidor: la base es un archivo que se copia como cualquier otro |
| Acceso a datos | Módulo `sqlite3` de Python, sin librerías extra | Menos código y dependencias. Un número de versión en la base (`PRAGMA user_version`) y scripts de actualización numerados permiten cambiar la estructura sin perder datos |
| Importes | `Decimal` o enteros en centavos | Evita errores de redondeo |
| Excel (leer y exportar) | openpyxl | Lee `.xlsx` y genera exportaciones |
| PDF | ReportLab | Estados de cuenta, recibos y cierres de caja, con el logo de IOS en el encabezado |
| Logo e ícono | Carpeta `assets/` con `logo.png` (fondo transparente, 512 × 512 px o más) e `ios.ico` generado a partir del logo, con tamaños 16, 32, 48 y 256 px | El mismo logo se usa en el ícono del programa, la barra de la ventana, la pantalla de inicio, los accesos directos, el instalador y los PDF |
| Pruebas | pytest | Cálculos y reglas con casos reales |
| Empaquetado | PyInstaller en modo carpeta, con `ios.ico` como ícono | Arma el programa con Python y todas las librerías adentro |
| Instalador | Inno Setup (gratuito, solo en la PC de desarrollo), con `ios.ico` como ícono | Un `Instalar IOS.exe` que copia el programa, crea el acceso directo en el escritorio y en el menú Inicio, y la carpeta de datos compartida `C:\ProgramData\IOS`. La primera vez que se abre, IOS crea la base vacía. Reinstalar o actualizar no toca la base |

**Capas del proyecto**, para que la interfaz no tenga lógica de negocio:

- `domain/`: reglas y cálculos puros (descuento, IVA, saldos, ganancia teórica).
- `data/`: modelos, migraciones y consultas.
- `services/`: casos de uso (cargar remito, asentar cobranza, anular recibo, importar Excel).
- `reports/`: generación de PDF y Excel.
- `ui/`: ventanas y formularios.
- `tests/`: pruebas de `domain/` y `services/` con una base temporal.

## Etapas de desarrollo

Cada etapa termina con algo que se puede abrir y probar. Se recomienda pasarlas a Code de a una.

1. **Base del proyecto.** Estructura de carpetas (incluida assets/ con logo e ícono), base SQLite con todas las tablas (incluidas las de caja), migraciones y módulo de cálculos con pruebas. Listo cuando las pruebas de descuento, IVA y saldos pasan.
2. **Clientes y sucursales.** Alta, edición y baja lógica, con el cliente Particulares. Listo cuando se puede cargar Croma con sus dos sucursales.
3. **Comprobantes.** Carga con descuento e IVA editables, IVA discriminado en columna, anulación, tipos configurables y control de números repetidos. Listo cuando se carga un mes de remitos sin tocar fórmulas.
4. **Cobranzas, recibos y cheques.** Un pago con una o varias formas de pago aplicado a varios remitos, pagos parciales, carga de cheques y recibo correlativo en PDF. Cada pago registra su movimiento de caja. Listo cuando el caso Del Pilar (un pago, cinco remitos) funciona.
5. **Cuenta corriente y estado de cuenta.** Movimientos por sucursal, total consolidado y PDF. Listo cuando el estado de cuenta de Croma muestra ambas sucursales y su total.
6. **Compras y pagos a proveedores.** Proveedores, facturas con IVA y depósitos. Cada pago registra su egreso de caja, también si se paga con un cheque en cartera. Listo cuando se carga una factura de Lentex y baja el IVA deuda.
7. **Caja diaria y cheques.** Pantalla de caja con gastos, retiros, aportes y transferencias internas; cierre con arqueo por forma de pago; ajuste del saldo inicial; contramovimientos por anulación; pantalla de cheques. Listo cuando un día con cobros mixtos, un pago, un gasto y un depósito al banco cierra con diferencia cero.
8. **Resumen mensual y dashboard.** Réplica de TOTALES para cualquier mes, con total disponible desde la caja, más indicadores de inicio. Listo cuando el resumen cierra con los datos de prueba.
9. **Importación y exportación de Excel.** Importación opcional con vista previa, anomalías y asignación de sucursales, y exportaciones para el contador. Listo cuando `MARZO 2024.xlsx` se importa y reproduce los totales esperados.
10. **Empaquetado y prueba real.** Generar el `.exe`, armar el instalador, instalarlo en la PC y usarlo un mes en paralelo con el Excel. Listo cuando los totales y la caja de ambos coinciden.

## Pruebas y validaciones

El Excel de marzo sirve como prueba de aceptación: sus tres totales de la hoja TOTALES deben reproducirse al importarlo.

| Total en `MARZO 2024.xlsx` | Valor |
| --- | --- |
| Total venta | 2.848.734,135 |
| Total pagos | 1.038.852,72 |
| Total saldos | 1.809.881,415 |

Pueden aparecer diferencias de centavos por la política de redondeo y por las anomalías que la importación señala (remitos repetidos, IVA tipeado a mano). Cada diferencia debe poder explicarse.

**Casos mínimos para `pytest`:**

- Remito de 4.416,40 con 20% de descuento e IVA SÍ: final 3.533,12 e IVA discriminado 613,19.
- Remito con 25% de descuento (Croma): 104.544 pasa a 78.408 con IVA discriminado 13.608.
- Remito con IVA NO: IVA 0 y final sin cambios.
- Cambiar la tasa de IVA en configuración cambia el cálculo de los remitos nuevos y no los ya cargados.
- Un recibo que cubre cinco remitos y deja saldos en cero.
- Un recibo pagado con efectivo y dos cheques: genera tres movimientos de caja y dos cheques en cartera.
- Un pago parcial que deja saldo en el remito.
- Un pago mayor al saldo deja el excedente como saldo a favor; aplicarlo después a un remito nuevo lo cancela sin generar movimiento de caja.
- Recibo anulado: los saldos vuelven a su valor anterior, sus cheques pasan a anulado y se genera el contramovimiento de caja.
- Anular un recibo de un día cerrado genera el contramovimiento en el día actual y no modifica el cierre anterior.
- Tipo + número repetido: la carga se rechaza y solo se guarda si se confirma.
- Agregar un cliente nuevo o cambiar de mes no modifica totales de otros clientes.
- Un recibo en efectivo suma a la caja del día; un pago a proveedor resta.
- Un depósito de efectivo al banco resta del efectivo, suma al banco y no cambia el total disponible.
- Cierre con arqueo distinto del teórico: registra la diferencia y exige nota.
- El saldo inicial propone el arqueo del cierre anterior; si se modifica, se crea un movimiento de ajuste con nota.
- Un recibo importado desde Excel no genera movimiento de caja.

* Con redondeo a 2 decimales, 1.654,786115 se guarda como 1.654,79; con 0 decimales, como 1.655.
* Si el número inicial de recibo es 70001 y ya existe, el siguiente recibo toma el inmediato superior libre.
* Un recibo de abril aplicado a un remito de marzo suma en los pagos de marzo.

## Puntos resueltos

No quedan puntos abiertos. Estas son las últimas definiciones, ya volcadas en las secciones correspondientes.

| Punto | Decisión | Etapa |
| --- | --- | --- |
| Pagos del mes | Pagos aplicados a remitos del mes | 8 |
| Redondeo | Configurable (cantidad de decimales, por defecto 2) | 1 |
| Numeración de recibos | Número inicial configurable; si ya existe, toma el inmediato superior libre | 4 |
| Estados del cheque | En cartera, cobrado, entregado a proveedor, rechazado y anulado | 4 |
| Copias de seguridad | Fuera de la primera versión | — |
