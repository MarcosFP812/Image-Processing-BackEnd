from datetime import datetime
from app import db # Importa la instancia db desde app.py

class ImageData(db.Model):
    __tablename__ = 'image_data'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    # Asegúrate de que el timestamp de Scala se pueda convertir a datetime
    # Usar DateTime con timezone es recomendable si Scala envía zona horaria (p.ej., ISO 8601 con 'Z')
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    filename = db.Column(db.String(255), nullable=False)
    red_count = db.Column(db.Integer, default=0)
    green_count = db.Column(db.Integer, default=0)
    blue_count = db.Column(db.Integer, default=0)
    other_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<ImageData {self.filename} by {self.username} at {self.timestamp}>'

    def to_dict(self):
        """Convierte el objeto a un diccionario para facilitar la serialización JSON."""
        return {
            'id': self.id,
            'username': self.username,
            # Formatea el timestamp a ISO 8601 para consistencia
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'filename': self.filename,
            'color_counts': {
                'Red': self.red_count,
                'Green': self.green_count,
                'Blue': self.blue_count,
                'Other': self.other_count
            }
        }