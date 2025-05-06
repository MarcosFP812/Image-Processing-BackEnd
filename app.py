import os
from flask import Flask, request, jsonify, render_template, abort, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timezone
from dateutil import parser # Para parsear fechas ISO 8601 de forma robusta

# --- Inicialización ---
app = Flask(__name__, static_folder='static', template_folder='templates')

# Carga la configuración (Development o Production)
from config import app_config
app.config.from_object(app_config)

# Inicializa extensiones
db = SQLAlchemy(app)
migrate = Migrate(app, db) # Para gestionar migraciones de BD

# Importa modelos DESPUÉS de inicializar db
from models import ImageData

# --- Creación de Tablas (Solo si no existen) ---
# En un entorno real con migraciones, esto se haría con 'flask db upgrade'
# Pero para un inicio rápido, esto asegura que la tabla exista la primera vez.
with app.app_context():
    print("Intentando crear tablas si no existen...")
    db.create_all()
    print("Llamada a db.create_all() completada.")

# --- Rutas de la API ---

@app.route('/upload_data', methods=['POST'])
def upload_data():
    """
    Endpoint para recibir datos desde la aplicación Scala.
    Espera un JSON con: filename, username, timestamp, color_counts (Map/Dict).
    """
    print("Recibida petición POST en /upload_data")
    if not request.is_json:
        print("Error: La petición no contiene JSON")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    print(f"Datos JSON recibidos: {data}")

    # Validación básica de campos requeridos
    required_fields = ['filename', 'username', 'timestamp', 'color_counts']
    if not all(field in data for field in required_fields):
        print(f"Error: Faltan campos requeridos. Necesarios: {required_fields}")
        return jsonify({"error": "Missing required fields"}), 400

    color_counts = data.get('color_counts', {})
    if not isinstance(color_counts, dict):
        print("Error: 'color_counts' debe ser un objeto JSON (diccionario).")
        return jsonify({"error": "'color_counts' must be an object"}), 400

    # Parsear timestamp (Scala envía ISO 8601)
    try:
        # Usamos dateutil.parser para más flexibilidad con formatos ISO 8601
        # Si el timestamp no tiene zona horaria, asumimos UTC
        timestamp_str = data['timestamp']
        parsed_timestamp = parser.isoparse(timestamp_str)
        # Si no tiene timezone info, lo hacemos 'aware' asumiendo UTC
        if parsed_timestamp.tzinfo is None:
             parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
        # Convertimos a UTC para almacenar de forma consistente
        timestamp_utc = parsed_timestamp.astimezone(timezone.utc)
        print(f"Timestamp parseado a UTC: {timestamp_utc}")

    except ValueError as e:
        print(f"Error parseando timestamp '{data['timestamp']}': {e}")
        return jsonify({"error": f"Invalid timestamp format: {e}"}), 400
    except Exception as e:
        print(f"Error inesperado procesando timestamp: {e}")
        return jsonify({"error": f"Error processing timestamp: {e}"}), 500


    # Crear instancia del modelo
    try:
        new_data = ImageData(
            filename=data['filename'],
            username=data['username'],
            timestamp=timestamp_utc,
            # Obtener conteos, con valor por defecto 0 si no vienen
            red_count=color_counts.get('Red', 0),
            green_count=color_counts.get('Green', 0),
            blue_count=color_counts.get('Blue', 0),
            other_count=color_counts.get('Other', 0)
        )
        print(f"Objeto ImageData creado: {new_data}")

        # Guardar en la base de datos
        db.session.add(new_data)
        db.session.commit()
        print("Datos guardados en la base de datos con éxito.")

        # Devolver respuesta de éxito
        # Usamos el método to_dict() si quieres devolver el objeto creado
        # return jsonify(new_data.to_dict()), 201
        return jsonify({"message": "Data received and stored successfully"}), 201

    except Exception as e:
        db.session.rollback() # Revertir cambios en caso de error
        print(f"Error al guardar en la base de datos: {e}")
        # Considera loggear el error completo aquí para depuración
        # import traceback
        # traceback.print_exc()
        return jsonify({"error": f"Database error: {str(e)}"}), 500

# --- Rutas del Visor Web ---

@app.route('/', methods=['GET'])
def view_data():
    """Muestra los datos almacenados en una tabla HTML."""
    print("Recibida petición GET en /")
    try:
        # Obtener la fecha actual para pasarla a la plantilla
        current_time = datetime.now()
        print(f"Fecha actual: {current_time}")
        
        # Recuperar todos los datos, ordenados por fecha descendente
        all_entries = ImageData.query.order_by(ImageData.timestamp.desc()).all()
        print(f"Recuperados {len(all_entries)} registros de la base de datos.")
        
        # Renderizar la plantilla HTML pasando los datos y la fecha actual
        return render_template('index.html', image_data_list=all_entries, now=current_time)
    except Exception as e:
        print(f"Error al recuperar datos para el visor web: {e}")
        # Loggear el error completo para depuración
        import traceback
        traceback.print_exc()
        # Mostrar página de error
        abort(500, description=f"Error retrieving data from database: {str(e)}")


@app.route('/get_data', methods=['GET'])
def get_data_api():
    """Endpoint API opcional para obtener todos los datos en formato JSON."""
    print("Recibida petición GET en /get_data")
    try:
        all_entries = ImageData.query.order_by(ImageData.timestamp.desc()).all()
        # Convierte cada objeto ImageData a un diccionario usando el método to_dict()
        data_list = [entry.to_dict() for entry in all_entries]
        print(f"Devolviendo {len(data_list)} registros como JSON.")
        return jsonify(data_list), 200
    except Exception as e:
        print(f"Error en API /get_data: {e}")
        return jsonify({"error": f"Failed to retrieve data: {str(e)}"}), 500

# --- Nueva ruta para eliminar registros ---
@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    """Elimina un registro de la base de datos según su ID."""
    print(f"Recibida petición para eliminar registro con ID: {record_id}")
    try:
        # Buscar el registro por ID
        record = ImageData.query.get_or_404(record_id)
        
        # Eliminar el registro
        db.session.delete(record)
        db.session.commit()
        print(f"Registro con ID {record_id} eliminado correctamente.")
        
        # Redirigir a la página principal
        return redirect(url_for('view_data'))
    except Exception as e:
        db.session.rollback()  # Revertir cambios en caso de error
        print(f"Error al eliminar registro {record_id}: {e}")
        # Loggear el error completo para depuración
        import traceback
        traceback.print_exc()
        abort(500, description=f"Error deleting record: {str(e)}")

# --- Ejecución (para desarrollo local) ---
if __name__ == '__main__':
    # Ejecuta `flask run` en la terminal en lugar de `python app.py`
    # `flask run` utiliza las variables de entorno FLASK_APP y FLASK_DEBUG
    print("Para ejecutar la aplicación localmente, usa el comando: flask run")
    # app.run() # No se recomienda para desarrollo con auto-reload, usa `flask run`