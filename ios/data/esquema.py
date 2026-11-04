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
