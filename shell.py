from app import db
from app import app
from app import User

with app.app_context():
    db.drop_all()   # Supprime toutes les tables
    db.create_all() # Recrée toutes les tables

