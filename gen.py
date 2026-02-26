# In Flask shell
from app import app
from models import db, User
with app.app_context():
    admin = User(first_name='Admin', last_name='User', email='mambubayoh3@gmail.com', phone='23280401927', is_admin=True, is_confirmed=True)
    admin.set_password('31210151')
    db.session.add(admin)
    db.session.commit()