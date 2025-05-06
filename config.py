import os
from dotenv import load_dotenv

# Carga las variables de entorno del archivo .env si existe (para desarrollo local)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

class Config:
    """Configuración base de la aplicación."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-dificil-de-adivinar'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = None # Se definirá en subclases

class DevelopmentConfig(Config):
    """Configuración para desarrollo local."""
    DEBUG = True
    # Lee la URL de la BD desde el archivo .env
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL_LOCAL') or \
                              'postgresql+psycopg2://user:password@host:port/dbname' # Cambia esto por defecto
    print("----- Loading Development Config -----")
    print(f"DB URI (local): {SQLALCHEMY_DATABASE_URI[:SQLALCHEMY_DATABASE_URI.find('://')+3]}... (Credentials hidden)")


class ProductionConfig(Config):
    """Configuración para producción en Azure."""
    DEBUG = False
    # Construye la URI de la base de datos usando variables de entorno de Azure App Service
    # Asegúrate de que estas variables (DBUSER, DBPASS, DBHOST, DBNAME) están configuradas
    # en la sección 'Configuración -> Configuración de la aplicación' de tu App Service
    # y que están conectadas a tu Key Vault.
    dbuser = os.environ.get('DBUSER')
    dbpass = os.environ.get('DBPASS')
    dbhost = os.environ.get('DBHOST')
    dbname = os.environ.get('DBNAME')

    if not all([dbuser, dbpass, dbhost, dbname]):
        print("¡ERROR! Variables de entorno de la base de datos no encontradas para producción.")
        # Podrías lanzar una excepción aquí o manejarlo como prefieras
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Fallback a memoria para evitar crash inmediato
    else:
        SQLALCHEMY_DATABASE_URI = f'postgresql+psycopg2://{dbuser}:{dbpass}@{dbhost}/{dbname}'
        print("----- Loading Production Config -----")
        print(f"DB URI (Azure): postgresql+psycopg2://<user>:<password>@{dbhost}/{dbname} (Credentials hidden)")


# Determina qué configuración usar
app_config = ProductionConfig if 'WEBSITE_HOSTNAME' in os.environ else DevelopmentConfig