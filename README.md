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
