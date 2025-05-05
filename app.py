import os
import psycopg2
from flask import Flask, request, jsonify, render_template, g
from dotenv import load_dotenv
import datetime

# Load environment variables for local development
# In Azure App Service, these will be set in the Configuration
load_dotenv()

app = Flask(__name__)

# --- Database Configuration ---
def get_db_config():
    """Gets database configuration from environment variables."""
    # Use Azure Service Connector variables if available, otherwise use .env file vars
    config = {
        "host": os.environ.get("AZURE_POSTGRESQL_HOST") or os.environ.get("DB_HOST"),
        "database": os.environ.get("AZURE_POSTGRESQL_DATABASE") or os.environ.get("DB_NAME"),
        "user": os.environ.get("AZURE_POSTGRESQL_USER") or os.environ.get("DB_USER"),
        "password": os.environ.get("AZURE_POSTGRESQL_PASSWORD") or os.environ.get("DB_PASSWORD"),
        "port": os.environ.get("DB_PORT", 5432), # Default to 5432 if not set
        "sslmode": os.environ.get("DB_SSLMODE", "require") # Default to require for Azure PG
    }
    # Basic validation
    if not all([config["host"], config["database"], config["user"], config["password"]]):
        raise ValueError("Database configuration is incomplete. Check environment variables.")
    return config

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        try:
            config = get_db_config()
            app.logger.info(f"Connecting to DB: host={config['host']}, db={config['database']}, user={config['user']}")
            g.db = psycopg2.connect(
                host=config["host"],
                database=config["database"],
                user=config["user"],
                password=config["password"],
                port=config["port"],
                sslmode=config["sslmode"] # Important for Azure PostgreSQL
            )
        except psycopg2.Error as e:
            app.logger.error(f"Database connection error: {e}")
            # Decide how to handle this - maybe return an error or raise exception
            raise ConnectionError(f"Could not connect to the database: {e}") from e
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
    if error:
      app.logger.error(f"App Context teardown error: {error}")

def init_db():
    """Initializes the database schema (creates table if not exists)."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_data (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                upload_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                username VARCHAR(100) NOT NULL,
                red_pixels INTEGER,
                green_pixels INTEGER,
                blue_pixels INTEGER,
                other_pixels INTEGER -- Pixels not matching R, G, or B, or grayscale pixels
            );
        """)
        db.commit()
        app.logger.info("Database table 'image_data' checked/created.")
    except psycopg2.Error as e:
        db.rollback() # Rollback in case of error during table creation
        app.logger.error(f"Error initializing database table: {e}")
    finally:
        cursor.close()

# Initialize DB on first request (alternative: run this manually or via a startup script)
@app.before_request
def before_request_func():
    # Only initialize DB once per application lifetime or check existence more carefully
    # For simplicity, let's try initializing on each request start, CREATE IF NOT EXISTS handles it.
    # A better approach might be using app.cli.command or checking a global flag.
    if not getattr(g, 'db_initialized', False):
      try:
        init_db()
        g.db_initialized = True # Mark as initialized for this app instance lifetime
      except ConnectionError as e:
         # Log or handle the fact that DB connection failed during init
         app.logger.error(f"DB initialization failed: {e}")
         # Maybe set a flag to prevent further DB operations or return error response

# --- API Endpoint ---
@app.route('/upload_data', methods=['POST'])
def upload_data():
    """Receives image processing data from Scala client and stores it."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    app.logger.info(f"Received data: {data}") # Log received data

    # Basic Validation
    required_fields = ['filename', 'username', 'timestamp', 'color_counts']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields", "required": required_fields}), 400
    if not isinstance(data['color_counts'], dict):
         return jsonify({"error": "'color_counts' must be an object"}), 400

    filename = data.get('filename')
    username = data.get('username')
    timestamp_str = data.get('timestamp') # Expecting ISO 8601 format string from Scala
    color_counts = data.get('color_counts', {})

    # Parse timestamp (handle potential errors)
    try:
        upload_time = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, TypeError) as e:
        app.logger.error(f"Invalid timestamp format: {timestamp_str}. Error: {e}")
        return jsonify({"error": f"Invalid timestamp format: {timestamp_str}. Use ISO 8601."}), 400

    # Extract counts (handle missing keys gracefully)
    red_pixels = color_counts.get('Red', 0)
    green_pixels = color_counts.get('Green', 0)
    blue_pixels = color_counts.get('Blue', 0)
    other_pixels = color_counts.get('Other', 0) # Or 'Gray' depending on Scala implementation

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO image_data (filename, upload_timestamp, username, red_pixels, green_pixels, blue_pixels, other_pixels)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (filename, upload_time, username, red_pixels, green_pixels, blue_pixels, other_pixels)
        )
        db.commit()
        cursor.close()
        app.logger.info(f"Data for {filename} by {username} inserted successfully.")
        return jsonify({"message": "Data uploaded successfully"}), 201
    except (psycopg2.Error, ConnectionError) as e:
        # Rollback in case of DB error during insert
        db_conn = g.get('db')
        if db_conn:
            db_conn.rollback()
        app.logger.error(f"Database error during insert: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500
    except Exception as e:
        # Catch other unexpected errors
        app.logger.error(f"Unexpected error during upload: {e}")
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500


# --- Web Visor Endpoint ---
@app.route('/view_data', methods=['GET'])
def view_data():
    """Retrieves data from the database and displays it in an HTML table."""
    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor) # Fetch rows as dictionaries
        # Fetch data ordered by timestamp descending
        cursor.execute("SELECT * FROM image_data ORDER BY upload_timestamp DESC")
        results = cursor.fetchall()
        cursor.close()
        # Render the HTML template, passing the data to it
        return render_template('view.html', image_entries=results)
    except (psycopg2.Error, ConnectionError) as e:
         app.logger.error(f"Database error during fetch: {e}")
         # Render an error page or return a simple error message
         return f"Error retrieving data from database: {e}", 500
    except Exception as e:
        app.logger.error(f"Unexpected error during view: {e}")
        return f"An unexpected error occurred: {e}", 500

# --- Root Endpoint (Optional) ---
@app.route('/')
def home():
    """Simple home page linking to the data viewer."""
    return """
    <h1>PECL2 Scala/Cloud Integration</h1>
    <p><a href="/view_data">View Uploaded Image Data</a></p>
    """

if __name__ == '__main__':
    # Set debug=True for local development ONLY
    # Azure App Service uses Gunicorn or another production server
    port = int(os.environ.get("PORT", 5000)) # Use PORT environment variable if available
    app.run(host='0.0.0.0', port=port, debug=False) # Set debug=False for production/Azure