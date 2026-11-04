# Capturas para el Manual del usuario

Guardar cada captura en esta carpeta con el nombre exacto de la lista (PNG o JPG, da igual la
extensión real siempre que el nombre de archivo sea el mismo que usa `docs/manual/generar_manual.py`
en cada llamada a `captura(...)`). Si falta alguna, el manual se genera igual: queda un
recuadro gris indicando qué captura falta en ese lugar.

Después de agregar o reemplazar capturas, regenerar el PDF:

```bash
.venv\Scripts\python.exe docs\manual\generar_manual.py
```

## Lista de capturas

| Archivo | Qué mostrar |
|---|---|
| `menu_principal.png` | Ventana principal de IOS, con el menú superior abierto (para ver los grupos). |
| `inicio.png` | Pantalla Inicio (Dashboard) completa. |
| `facturacion.png` | Facturación con un cliente elegido y un remito a medio cargar. |
| `comprobantes.png` | Comprobantes con algún filtro de fechas aplicado y resultados en la tabla. |
| `cobranzas.png` | Cobranzas con remitos tildados y al menos una forma de pago cargada. |
| `cobranzas_caja_cerrada.png` | El aviso ("La caja de hoy está cerrada...") al confirmar un cobro sin la caja abierta. |
| `cuenta_corriente.png` | Cuenta corriente mostrando el saldo de un cliente por sucursal. |
| `clientes.png` | Lista de Clientes, con el buscador/filtro de arriba. |
| `clientes_dialogo.png` | La ventana de alta/edición de un cliente (pestañas Datos/Sucursales). |
| `compras_proveedores.png` | Pestaña Compras, con la tasa de IVA elegida. |
| `pagos_proveedores.png` | Pestaña Pagos a proveedores, con un pago cargado. |
| `caja_diaria.png` | Pestaña "Hoy" de Caja diaria, con movimientos cargados. |
| `abrir_caja.png` | La ventana de "Abrir caja", con el saldo propuesto por forma de pago. |
| `cheques.png` | Cheques en cartera. |
| `gastos_caja_chica.png` | Gastos de caja chica, con algún total por categoría. |
| `resumen_mensual.png` | Pestaña Resumen de Resumen mensual. |
| `resumen_mensual_graficos.png` | Pestaña Gráficos de Resumen mensual. |
| `compras_por_cliente.png` | Compras por cliente (detalle o ranking). |
| `deudores.png` | Deudores, con algunos clientes listados. |
| `iva_mes.png` | IVA del mes. |
| `flujo_caja.png` | Flujo de caja. |
| `exportacion_contador.png` | Exportación para el contador. |
| `importar_excel.png` | Importar desde Excel, con una vista previa y conflictos detectados. |
| `configuracion.png` | Pestaña General de Configuración. |
| `configuracion_mantenimiento.png` | Pestaña Mantenimiento de Configuración. |

No hace falta mandarlas todas juntas: se pueden ir agregando de a poco y regenerando el manual
cada vez.
