# Cuadrante

Aplicación de escritorio para crear y controlar los cuadrantes semanales del restaurante.

## Funciones actuales

- Turnos semanales de lunes a domingo.
- Estados diferenciados: Descanso, Propio, Baja y Falta.
- Recuento de trabajadores por desayuno, almuerzo y cena sin depender de las letras del código.
- Aviso de apertura ausente o duplicada.
- Gestión de empleados y catálogo de turnos.
- Umbrales de cobertura configurables.
- Tema claro/oscuro persistente, nombre, logo y tamaño de fuente.
- Exportación a PDF y copias automáticas de la base de datos en OneDrive.

## Inicio

Instala las dependencias con `pip install -r requirements.txt` y ejecuta `python app.py`, o usa `iniciar_app.bat` en Windows.

## Versión portable para Windows

Con PyInstaller instalado, ejecuta `build_portable.ps1`. El paquete se genera en `release/` y mantiene sus datos junto al ejecutable.

## Versiones automáticas para Windows y Linux

Al publicar un release en GitHub, la acción `Crear versiones portables` ejecuta las pruebas, compila la aplicación en Windows x64 y Linux x64 y adjunta ambos paquetes al release. También puede ejecutarse manualmente desde la pestaña Actions para descargar paquetes de prueba sin publicar una versión.

La compilación de Linux se realiza realmente en Linux: PyInstaller no permite generar este ejecutable desde Windows. En Linux, la carpeta de copias puede seleccionarse manualmente en Ajustes; la detección automática de OneDrive solo está disponible en Windows.
