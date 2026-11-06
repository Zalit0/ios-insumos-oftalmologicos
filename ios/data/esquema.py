"""Esquema SQLite de IOS: migración 1, todas las tablas del plan.

Cada campo de importe o porcentaje usa el tipo declarado ``DECIMAL_TEXT``
(ver ios/data/db.py) para guardarse y leerse como ``decimal.Decimal``.

El nombre tiene que contener "TEXT": así SQLite le asigna afinidad TEXT a
la columna. Si se llamara simplemente ``DECIMAL``, SQLite le asignaría
afinidad NUMERIC (no contiene "INT", "CHAR/CLOB/TEXT", "BLOB" ni
"REAL/FLOA/DOUB") y guardaría el valor como ``REAL`` (float de 64 bits) en
lugar del texto exacto que escribe el adapter de ``Decimal`` — justo lo que
se busca evitar.
"""

MIGRACION_1_ESQUEMA = """
CREATE TABLE clientes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL,
    cuit                TEXT,
    telefono            TEXT,
    direccion           TEXT,
    localidad           TEXT,
    descuento_default   DECIMAL_TEXT NOT NULL DEFAULT '0',
    con_iva_default     INTEGER NOT NULL DEFAULT 1 CHECK (con_iva_default IN (0, 1)),
    es_particular       INTEGER NOT NULL DEFAULT 0 CHECK (es_particular IN (0, 1)),
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE TABLE sucursales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER NOT NULL REFERENCES clientes (id),
    nombre      TEXT NOT NULL,
    UNIQUE (cliente_id, nombre)
);

CREATE INDEX ix_sucursales_cliente ON sucursales (cliente_id);

CREATE TABLE tipos_comprobante (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL,
    abreviatura TEXT NOT NULL UNIQUE,
    activo      INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE TABLE formas_pago (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT NOT NULL,
    tipo    TEXT NOT NULL CHECK (tipo IN ('efectivo', 'banco', 'cheque', 'otro')),
    activo  INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE TABLE comprobantes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_comprobante_id INTEGER NOT NULL REFERENCES tipos_comprobante (id),
    numero              TEXT NOT NULL,
    fecha               TEXT NOT NULL,
    cliente_id          INTEGER NOT NULL REFERENCES clientes (id),
    sucursal_id         INTEGER NOT NULL REFERENCES sucursales (id),
    nombre_particular   TEXT,
    monto_lista         DECIMAL_TEXT NOT NULL,
    descuento_pct       DECIMAL_TEXT NOT NULL DEFAULT '0',
    monto_final         DECIMAL_TEXT NOT NULL,
    con_iva             INTEGER NOT NULL DEFAULT 0 CHECK (con_iva IN (0, 1)),
    iva_discriminado    DECIMAL_TEXT NOT NULL DEFAULT '0',
    notas               TEXT,
    estado              TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'anulado'))
);

-- No es UNIQUE: tipo + número repetido se detecta y confirma en services/,
-- no se rechaza a nivel de base (docs/PLAN.md, "Integridad").
CREATE INDEX ix_comprobantes_tipo_numero ON comprobantes (tipo_comprobante_id, numero);
CREATE INDEX ix_comprobantes_cliente ON comprobantes (cliente_id);
CREATE INDEX ix_comprobantes_fecha ON comprobantes (fecha);

CREATE TABLE recibos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    numero      INTEGER NOT NULL UNIQUE,
    fecha       TEXT NOT NULL,
    cliente_id  INTEGER NOT NULL REFERENCES clientes (id),
    monto_total DECIMAL_TEXT NOT NULL,
    origen      TEXT NOT NULL DEFAULT 'manual' CHECK (origen IN ('manual', 'importado')),
    estado      TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'anulado'))
);

CREATE INDEX ix_recibos_cliente ON recibos (cliente_id);

CREATE TABLE cheques (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero              TEXT NOT NULL,
    cliente_id          INTEGER NOT NULL REFERENCES clientes (id),
    banco               TEXT,
    monto               DECIMAL_TEXT NOT NULL,
    fecha_cobro         TEXT NOT NULL,
    recibo_origen_id    INTEGER REFERENCES recibos (id),
    estado              TEXT NOT NULL DEFAULT 'en_cartera'
                        CHECK (estado IN ('en_cartera', 'cobrado', 'entregado_a_proveedor',
                                           'rechazado', 'anulado'))
);

CREATE INDEX ix_cheques_fecha_cobro ON cheques (fecha_cobro);

CREATE TABLE recibo_pagos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recibo_id       INTEGER NOT NULL REFERENCES recibos (id),
    forma_pago_id   INTEGER NOT NULL REFERENCES formas_pago (id),
    monto           DECIMAL_TEXT NOT NULL,
    cheque_id       INTEGER REFERENCES cheques (id)
);

CREATE INDEX ix_recibo_pagos_recibo ON recibo_pagos (recibo_id);

CREATE TABLE aplicaciones_pago (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recibo_id       INTEGER NOT NULL REFERENCES recibos (id),
    comprobante_id  INTEGER NOT NULL REFERENCES comprobantes (id),
    monto_aplicado  DECIMAL_TEXT NOT NULL
);

CREATE INDEX ix_aplicaciones_pago_recibo ON aplicaciones_pago (recibo_id);
CREATE INDEX ix_aplicaciones_pago_comprobante ON aplicaciones_pago (comprobante_id);

CREATE TABLE proveedores (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT NOT NULL,
    cuit    TEXT
);

CREATE TABLE compras (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id    INTEGER NOT NULL REFERENCES proveedores (id),
    fecha           TEXT NOT NULL,
    numero_factura  TEXT NOT NULL,
    monto           DECIMAL_TEXT NOT NULL,
    iva             DECIMAL_TEXT NOT NULL DEFAULT '0'
);

CREATE INDEX ix_compras_proveedor ON compras (proveedor_id);
CREATE INDEX ix_compras_fecha ON compras (fecha);

CREATE TABLE pagos_proveedor (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id        INTEGER NOT NULL REFERENCES proveedores (id),
    fecha               TEXT NOT NULL,
    monto               DECIMAL_TEXT NOT NULL,
    forma_pago_id       INTEGER NOT NULL REFERENCES formas_pago (id),
    cheque_entregado_id INTEGER REFERENCES cheques (id),
    referencia          TEXT
);

CREATE INDEX ix_pagos_proveedor_proveedor ON pagos_proveedor (proveedor_id);
CREATE INDEX ix_pagos_proveedor_fecha ON pagos_proveedor (fecha);

CREATE TABLE categorias_caja (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT NOT NULL,
    tipo    TEXT NOT NULL CHECK (tipo IN ('ingreso', 'egreso')),
    activo  INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE TABLE cierres_caja (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha   TEXT NOT NULL UNIQUE,
    nota    TEXT,
    estado  TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'cerrado'))
);

CREATE TABLE movimientos_caja (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora              TEXT NOT NULL,
    tipo                    TEXT NOT NULL CHECK (tipo IN ('ingreso', 'egreso')),
    forma_pago_id           INTEGER NOT NULL REFERENCES formas_pago (id),
    monto                   DECIMAL_TEXT NOT NULL,
    categoria_id            INTEGER REFERENCES categorias_caja (id),
    concepto                TEXT,
    origen                  TEXT NOT NULL
                            CHECK (origen IN ('recibo', 'pago_proveedor', 'anulacion',
                                               'transferencia_interna',
                                               'ajuste_saldo_inicial', 'manual')),
    movimiento_relacionado_id INTEGER REFERENCES movimientos_caja (id),
    cierre_id               INTEGER REFERENCES cierres_caja (id)
);

CREATE INDEX ix_movimientos_caja_fecha_hora ON movimientos_caja (fecha_hora);
CREATE INDEX ix_movimientos_caja_cierre ON movimientos_caja (cierre_id);

CREATE TABLE cierres_caja_detalle (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cierre_id       INTEGER NOT NULL REFERENCES cierres_caja (id),
    forma_pago_id   INTEGER NOT NULL REFERENCES formas_pago (id),
    saldo_inicial   DECIMAL_TEXT NOT NULL,
    ingresos        DECIMAL_TEXT NOT NULL DEFAULT '0',
    egresos         DECIMAL_TEXT NOT NULL DEFAULT '0',
    saldo_teorico   DECIMAL_TEXT NOT NULL,
    arqueo          DECIMAL_TEXT,
    diferencia      DECIMAL_TEXT,
    UNIQUE (cierre_id, forma_pago_id)
);

CREATE TABLE configuracion (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    iva_pct                 DECIMAL_TEXT NOT NULL,
    comision_pct            DECIMAL_TEXT NOT NULL,
    numero_inicial_recibo   INTEGER NOT NULL,
    redondeo_decimales      INTEGER NOT NULL
);
"""

MIGRACION_1_DATOS_INICIALES = """
INSERT INTO tipos_comprobante (nombre, abreviatura, activo) VALUES ('Remito', 'RTO', 1);

INSERT INTO formas_pago (nombre, tipo, activo) VALUES
    ('Efectivo', 'efectivo', 1),
    ('Transferencia', 'banco', 1),
    ('Cheque', 'cheque', 1);

INSERT INTO configuracion (id, iva_pct, comision_pct, numero_inicial_recibo, redondeo_decimales)
VALUES (1, '21', '15', 1, 2);

INSERT INTO clientes (nombre, descuento_default, con_iva_default, es_particular, activo)
VALUES ('Particulares', '0', 1, 1, 1);

INSERT INTO sucursales (cliente_id, nombre)
VALUES ((SELECT id FROM clientes WHERE nombre = 'Particulares'), 'Principal');
"""

# docs/AJUSTES_V1.1.md, etapa 4: una sucursal se puede desactivar (pero
# nunca dejar a un cliente sin ninguna sucursal activa).
MIGRACION_2_ESQUEMA = """
ALTER TABLE sucursales ADD COLUMN activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1));
"""

# docs/AJUSTES_V1.1.md, etapa 5 (D2, D3): el IVA de una compra se calcula
# solo a partir del monto (con IVA incluido) y la tasa; se puede corregir a
# mano, lo que la marca "IVA manual". Las compras ya cargadas no tienen una
# tasa conocida, así que quedan marcadas como manuales.
MIGRACION_3_ESQUEMA = """
ALTER TABLE compras ADD COLUMN tasa_iva DECIMAL_TEXT NOT NULL DEFAULT '21';
ALTER TABLE compras ADD COLUMN iva_manual INTEGER NOT NULL DEFAULT 0 CHECK (iva_manual IN (0, 1));

UPDATE compras SET iva_manual = 1;
"""

# docs/AJUSTES_V1.1.md, etapa 7: al importar un recibo con número no
# numérico (TRANSF, S/R, S/N...) se le asigna un número automático y el
# texto original queda como referencia.
MIGRACION_4_ESQUEMA = """
ALTER TABLE recibos ADD COLUMN referencia TEXT;
"""

# Un cobro con fecha de un día cuya caja ya está cerrada no puede pegar en
# ese cierre (ya cerrado, no se reabre): su movimiento de caja se registra
# con la fecha de hoy para que entre en el arqueo del día. Esta nota queda
# para quien hace el cierre, aclarando por qué el movimiento no coincide
# con la fecha del recibo.
MIGRACION_5_ESQUEMA = """
ALTER TABLE movimientos_caja ADD COLUMN nota TEXT;
"""

# Catálogo de tipos de cristal (etapa 1 del plan de detalle de comprobantes):
# base para elegir un cristal al cargar un renglón, en vez de tipear el
# nombre cada vez. "vendido_por" distingue cristales (se venden por par,
# precio_unitario = precio_lista / 2) de accesorios como pegatinas (se
# venden por unidad/rollo, precio_unitario = precio_lista). "reponible"
# excluye del reporte de reposición ítems de stock que no se reponen (ej.
# minerales "hasta agotar stock").
MIGRACION_6_ESQUEMA = """
CREATE TABLE tipos_cristal (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL,
    categoria           TEXT,
    precio_lista        DECIMAL_TEXT NOT NULL DEFAULT '0',
    vendido_por         TEXT NOT NULL DEFAULT 'par' CHECK (vendido_por IN ('par', 'unidad')),
    requiere_graduacion INTEGER NOT NULL DEFAULT 1 CHECK (requiere_graduacion IN (0, 1)),
    reponible           INTEGER NOT NULL DEFAULT 1 CHECK (reponible IN (0, 1)),
    activo              INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE INDEX ix_tipos_cristal_nombre ON tipos_cristal (nombre);
"""

# Detalle (renglones) de un comprobante (plan de detalle de comprobantes,
# etapa 2): opcional — un comprobante cargado con la carga rápida de hoy
# simplemente no tiene filas acá. "graduacion" nunca puede quedar vacía
# cuando el tipo de cristal la requiere (se valida en services/, no acá).
# "pedido_especial_linea_id" no tiene REFERENCES todavía porque la tabla
# "pedido_lineas" se crea recién en una etapa posterior del plan (SQLite no
# valida FK contra una tabla inexistente mientras la columna quede en NULL,
# que es el único valor posible hasta esa etapa); se deja comentado acá para
# que quede documentada la intención.
MIGRACION_7_ESQUEMA = """
CREATE TABLE detalle_comprobante (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    comprobante_id               INTEGER NOT NULL REFERENCES comprobantes (id),
    tipo_cristal_id               INTEGER REFERENCES tipos_cristal (id),
    descripcion                  TEXT,
    graduacion                   TEXT NOT NULL,
    cantidad                     INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario               DECIMAL_TEXT NOT NULL,
    subtotal                     DECIMAL_TEXT NOT NULL,
    pedido_especial_linea_id      INTEGER  -- REFERENCES pedido_lineas (id), etapa futura
);

CREATE INDEX ix_detalle_comprobante_comprobante ON detalle_comprobante (comprobante_id);
"""

# Pedidos a proveedor (plan de detalle de comprobantes, etapa 4): cabecera
# + líneas, con dos orígenes — "reposicion" (se generan solas desde el
# reporte de ventas de stock) y "especial" (cargadas a mano, cristales que
# no hay en stock y se piden on-demand). El "estado" de la línea ya incluye
# los pasos de aprobación del cliente (etapa 5: a veces el proveedor manda
# una graduación aproximada y hay que confirmarla antes de entregar), aunque
# en esta etapa el flujo solo usa 'pedido' y 'recibido'.
MIGRACION_8_ESQUEMA = """
CREATE TABLE pedidos_proveedor (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id    INTEGER NOT NULL REFERENCES proveedores (id),
    fecha           TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'cerrado'))
);

CREATE INDEX ix_pedidos_proveedor_proveedor ON pedidos_proveedor (proveedor_id);

CREATE TABLE pedido_lineas (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id               INTEGER NOT NULL REFERENCES pedidos_proveedor (id),
    tipo_cristal_id         INTEGER REFERENCES tipos_cristal (id),
    descripcion             TEXT,
    cantidad                INTEGER NOT NULL CHECK (cantidad > 0),
    origen                  TEXT NOT NULL CHECK (origen IN ('reposicion', 'especial')),
    cliente_id              INTEGER REFERENCES clientes (id),
    graduacion_solicitada   TEXT,
    graduacion_recibida     TEXT,
    estado                  TEXT NOT NULL DEFAULT 'pedido'
                            CHECK (estado IN ('pedido', 'recibido', 'pendiente_aprobacion',
                                               'aprobado', 'rechazado', 'entregado'))
);

CREATE INDEX ix_pedido_lineas_pedido ON pedido_lineas (pedido_id);
"""

# El estado del pedido pasa de 'abierto'/'cerrado' a tres pasos explícitos
# que reflejan el proceso real: se arma ('en_carga'), se le manda al
# proveedor ('realizado') y llega ('recibido'). SQLite no permite cambiar un
# CHECK existente con ALTER TABLE, así que se recrea la tabla preservando
# los ids (de los que dependen las líneas) y migrando los valores viejos.
MIGRACION_9_ESQUEMA = """
PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

ALTER TABLE pedidos_proveedor RENAME TO pedidos_proveedor_viejo;

CREATE TABLE pedidos_proveedor (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id    INTEGER NOT NULL REFERENCES proveedores (id),
    fecha           TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'en_carga'
                    CHECK (estado IN ('en_carga', 'realizado', 'recibido'))
);

INSERT INTO pedidos_proveedor (id, proveedor_id, fecha, estado)
SELECT id, proveedor_id, fecha,
       CASE estado WHEN 'abierto' THEN 'en_carga' WHEN 'cerrado' THEN 'recibido' ELSE estado END
FROM pedidos_proveedor_viejo;

DROP TABLE pedidos_proveedor_viejo;

CREATE INDEX ix_pedidos_proveedor_proveedor ON pedidos_proveedor (proveedor_id);

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
"""

# Devolución de un cliente (plan de detalle de comprobantes, etapa 5.1): se
# anula el comprobante (no se cobra; todavía no se maneja stock real). Si lo
# devuelto era de stock y ese cristal/graduación ya se había vuelto a pedir
# al proveedor antes de la devolución, queda acá una "compensación" para no
# pedirlo de más la próxima vez que se genere la reposición de esa
# combinación — una fila por (tipo_cristal, graduación), acumulando
# cantidad; se borra sola cuando se termina de usar.
MIGRACION_10_ESQUEMA = """
CREATE TABLE compensaciones_reposicion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_cristal_id INTEGER NOT NULL REFERENCES tipos_cristal (id),
    graduacion      TEXT NOT NULL,
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0)
);

CREATE UNIQUE INDEX ix_compensaciones_reposicion_tipo_grad
    ON compensaciones_reposicion (tipo_cristal_id, graduacion);
"""

# Evita pedir dos veces lo mismo cuando se genera la reposición con rangos
# de fechas que se superponen (p. ej. un pedido del día 1, y a los 3 días
# otro del día 1 al 3: sin esto, lo vendido el día 1 se cuenta las dos
# veces). Cada renglón de venta de stock queda marcado apenas se usa en un
# pedido de reposición — se mire o no se mire de nuevo ese rango de fechas,
# no vuelve a contarse.
MIGRACION_11_ESQUEMA = """
ALTER TABLE detalle_comprobante ADD COLUMN incluido_en_reposicion INTEGER NOT NULL DEFAULT 0
    CHECK (incluido_en_reposicion IN (0, 1));
"""

# Reemplaza los estados de línea de la etapa 5 (que incluían un paso de
# aprobación que se sacó) por los que realmente hacen falta al recibir un
# pedido: cada línea se resuelve a mano, cristal por cristal, con uno de
# cuatro resultados posibles, antes de poder cerrar el pedido — 'pedido' es
# el único estado "sin resolver" (bloquea "Marcar pedido recibido").
# 'pendiente_aprobacion'/'aprobado' (llegaron, con o sin diferencia) pasan a
# 'recibido_con_diferencia'; 'rechazado' (no se entregaba) pasa a
# 'cancelado'. Mismo motivo que la migración 9 para recrear la tabla: SQLite
# no permite cambiar un CHECK existente con ALTER TABLE.
MIGRACION_12_ESQUEMA = """
PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

ALTER TABLE pedido_lineas RENAME TO pedido_lineas_viejo;

CREATE TABLE pedido_lineas (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id               INTEGER NOT NULL REFERENCES pedidos_proveedor (id),
    tipo_cristal_id         INTEGER REFERENCES tipos_cristal (id),
    descripcion             TEXT,
    cantidad                INTEGER NOT NULL CHECK (cantidad > 0),
    origen                  TEXT NOT NULL CHECK (origen IN ('reposicion', 'especial')),
    cliente_id              INTEGER REFERENCES clientes (id),
    graduacion_solicitada   TEXT,
    graduacion_recibida     TEXT,
    estado                  TEXT NOT NULL DEFAULT 'pedido'
                            CHECK (estado IN ('pedido', 'recibido', 'recibido_con_diferencia',
                                               'pendiente', 'cancelado', 'entregado'))
);

INSERT INTO pedido_lineas (id, pedido_id, tipo_cristal_id, descripcion, cantidad, origen,
                           cliente_id, graduacion_solicitada, graduacion_recibida, estado)
SELECT id, pedido_id, tipo_cristal_id, descripcion, cantidad, origen,
       cliente_id, graduacion_solicitada, graduacion_recibida,
       CASE estado
           WHEN 'pendiente_aprobacion' THEN 'recibido_con_diferencia'
           WHEN 'aprobado' THEN 'recibido_con_diferencia'
           WHEN 'rechazado' THEN 'cancelado'
           ELSE estado
       END
FROM pedido_lineas_viejo;

DROP TABLE pedido_lineas_viejo;

CREATE INDEX ix_pedido_lineas_pedido ON pedido_lineas (pedido_id);

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
"""

# Vincula una compra (factura de proveedor) con el pedido que la generó, al
# marcarlo recibido — para encontrarla después desde el pedido, y para no
# tener que volver a tipear proveedor/fecha a mano en esa pantalla.
MIGRACION_13_ESQUEMA = """
ALTER TABLE compras ADD COLUMN pedido_id INTEGER REFERENCES pedidos_proveedor (id);
"""
