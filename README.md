# IOS — Insumos Oftalmológicos Santiago

App de escritorio (Windows) para cuentas corrientes y caja de la distribuidora,
en reemplazo de la planilla de Excel. La especificación completa está en
[docs/PLAN.md](docs/PLAN.md); no se implementa nada que no esté ahí.

## Estado

Las 10 etapas del plan están completas: base del proyecto, clientes y
sucursales, comprobantes, cobranzas/recibos/cheques, cuenta corriente,
compras y proveedores, caja diaria, resumen mensual y dashboard, importación
desde Excel, reportes (PDF/Excel), interfaz PySide6 y empaquetado.

## Crear el entorno

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Correr las pruebas

```bash
pytest
```

## Correr la app

```bash
python main.py
```

## Base de datos

Por defecto la base vive en `C:\ProgramData\IOS\ios.db`. Para usar otra ruta
(desarrollo o pruebas) se define la variable de entorno `IOS_DB_PATH` con la
ruta completa del archivo `.db` antes de levantar la app o correr las pruebas.

## Capas

- `ios/domain/`: cálculos puros, sin acceso a base de datos ni a la interfaz.
- `ios/data/`: esquema, migraciones (`PRAGMA user_version`) y conexión sqlite3.
- `ios/services/`: casos de uso (altas, cobranzas, caja, importación...).
- `ios/reports/`: generación de PDF (ReportLab) y Excel (openpyxl).
- `ios/ui/`: ventana principal y pantallas PySide6; no tiene lógica de negocio.
- `ios/recursos.py`: resuelve la ruta de `assets/` (logo, ícono), sirve tanto
  corriendo desde el código fuente como empaquetado con PyInstaller.
- `tests/`: pruebas de todas las capas, incluidas pruebas de humo y
  funcionales de la interfaz (con `QT_QPA_PLATFORM=offscreen`).

## Empaquetado (etapa 10)

### 1. Generar el `.exe` con PyInstaller (modo carpeta)

```bash
pyinstaller --name IOS --onedir --windowed --icon assets/ios.ico --add-data "assets;assets" --noconfirm main.py
```

Esto arma `dist/IOS/` con `IOS.exe` y todo lo necesario para correr (incluida
una copia de `assets/`). Se puede probar ese `.exe` directamente antes de
armar el instalador.

### 2. Armar el instalador con Inno Setup

Hace falta tener [Inno Setup](https://jrsoftware.org/isinfo.php) instalado
en la PC de desarrollo (gratuito; no hace falta en la PC donde se usa IOS).
Con `dist/IOS/` ya generado:

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador\ios_setup.iss
```

(Según cómo se instaló, puede estar en otra carpeta — por ejemplo
`%LocalAppData%\Programs\Inno Setup 6\ISCC.exe` en vez de "Program Files
(x86)". Si el comando de arriba no encuentra el archivo, buscar `ISCC.exe`
en el sistema.)

Genera `instalador\Output\Instalar IOS.exe`, que:

- Copia el programa a Archivos de programa.
- Crea el acceso directo en el menú Inicio (y, si se tilda, en el escritorio).
- Crea la carpeta de datos compartida `C:\ProgramData\IOS` (la base la crea
  IOS solo, la primera vez que se abre).
- Nunca toca `C:\ProgramData\IOS\ios.db` al reinstalar, actualizar o
  desinstalar: esa carpeta no es parte de los archivos que instala o borra
  Inno Setup, así que los datos sobreviven sin importar cuántas veces se
  reinstale o actualice el programa.

### 3. Prueba real

Instalar en la PC, cargar un mes en paralelo con el Excel, y confirmar que
los totales (`Resumen mensual`) y la caja (`Caja diaria`) coinciden con los
de la planilla.
