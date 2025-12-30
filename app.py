from flask import Flask
from flask_socketio import SocketIO
import os
from routes import app_routes
from mqtt_handlers import start_threads, set_socketio_instance

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.environ.get('FLASK_SECRET_KEY', 'development'))
socketio = SocketIO(app)

# Pass socketio to mqtt_handlers
set_socketio_instance(socketio)

# Register routes
app.register_blueprint(app_routes)

if __name__ == '__main__':
    start_threads()
    socketio.run(app, host='0.0.0.0', port=5000)
