import os
import base64
from flask import (
    Flask, request, jsonify, render_template,
    abort, redirect, url_for, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timezone
from dateutil import parser  # Para parsear fechas ISO 8601 de forma robusta

# --- Inicialización ---
app = Flask(__name__, static_folder='static', template_folder='templates')

# Carga la configuración (Development o Production)
from config import app_config
app.config.from_object(app_config)

# Asegurarnos de que exista la carpeta donde guardaremos imágenes
# Define UPLOAD_FOLDER en config.py:
#   UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploaded_images')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Inicializa extensiones
db = SQLAlchemy(app)
migrate = Migrate(app, db)  # Para gestionar migraciones de BD

# Importa modelos DESPUÉS de inicializar db
from models import ImageData

# --- Ruta para servir imágenes subidas ---
@app.route('/uploaded_images/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Creación de Tablas (Solo si no existen) ---
with app.app_context():
    print("Intentando crear tablas si no existen...")
    db.create_all()
    print("Llamada a db.create_all() completada.")

# --- Rutas de la API ---
@app.route('/upload_data', methods=['POST'])
def upload_data():
    """
    Endpoint para recibir datos + imagen desde la aplicación Scala.
    Espera JSON con: filename, username, timestamp, color_counts, image_base64.
    """
    print("Recibida petición POST en /upload_data")
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    print(f"Datos JSON recibidos: {data}")

    # Campos requeridos
    required = ['filename', 'username', 'timestamp', 'color_counts', 'image_base64']
    if not all(f in data for f in required):
        return jsonify({"error": f"Missing fields: {required}"}), 400

    # Validar color_counts
    color_counts = data['color_counts']
    if not isinstance(color_counts, dict):
        return jsonify({"error": "'color_counts' must be an object"}), 400

    # Parsear timestamp ISO 8601
    try:
        ts = parser.isoparse(data['timestamp'])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        timestamp_utc = ts.astimezone(timezone.utc)
    except Exception as e:
        return jsonify({"error": f"Invalid timestamp: {e}"}), 400

    # Decodificar y guardar la imagen
    try:
        b64 = data['image_base64']
        img_bytes = base64.b64decode(b64)
        save_name = data['filename']
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], save_name)
        with open(save_path, 'wb') as f:
            f.write(img_bytes)
        print(f"Imagen guardada en: {save_path}")
    except Exception as e:
        return jsonify({"error": f"Failed to save image: {e}"}), 500

    # Crear instancia del modelo y guardar en BD
    try:
        new_data = ImageData(
            filename=data['filename'],
            # image_path=save_path,  # si tu modelo lo admite
            username=data['username'],
            timestamp=timestamp_utc,
            red_count=color_counts.get('Red', 0),
            green_count=color_counts.get('Green', 0),
            blue_count=color_counts.get('Blue', 0),
            other_count=color_counts.get('Other', 0)
        )
        db.session.add(new_data)
        db.session.commit()
        print("Datos e imagen guardados en la base de datos con éxito.")
        return jsonify({"message": "Data and image stored successfully"}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error al guardar en la base de datos: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500

# --- Rutas del Visor Web ---
@app.route('/', methods=['GET'])
def view_data():
    print("Recibida petición GET en /")
    try:
        current_time = datetime.now()
        all_entries = ImageData.query.order_by(ImageData.timestamp.desc()).all()
        return render_template('index.html', image_data_list=all_entries, now=current_time)
    except Exception as e:
        print(f"Error al recuperar datos: {e}")
        abort(500, description=str(e))

@app.route('/get_data', methods=['GET'])
def get_data_api():
    print("Recibida petición GET en /get_data")
    try:
        all_entries = ImageData.query.order_by(ImageData.timestamp.desc()).all()
        data_list = [entry.to_dict() for entry in all_entries]
        return jsonify(data_list), 200
    except Exception as e:
        print(f"Error en API /get_data: {e}")
        return jsonify({"error": f"Failed to retrieve data: {e}"}), 500

@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    print(f"Recibida petición para eliminar registro con ID: {record_id}")
    try:
        record = ImageData.query.get_or_404(record_id)
        db.session.delete(record)
        db.session.commit()
        print(f"Registro con ID {record_id} eliminado correctamente.")
        return redirect(url_for('view_data'))
    except Exception as e:
        db.session.rollback()
        print(f"Error al eliminar registro {record_id}: {e}")
        abort(500, description=f"Error deleting record: {e}")

# --- Ejecución (para desarrollo local) ---
if __name__ == '__main__':
    print("Para ejecutar la aplicación localmente, usa el comando: flask run")
    # app.run()  # No se recomienda para desarrollo con auto-reload, usa `flask run`
