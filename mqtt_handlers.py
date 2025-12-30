import paho.mqtt.client as mqtt
import threading
from database import insert_data, get_db_connection
import json
from datetime import datetime, timedelta
from flask_socketio import SocketIO, emit

timestamp_format = '%Y-%m-%d %H:%M:%S'


socketio_instance = None
topics = {}
active_mqtt_clients = {}

def set_socketio_instance(socketio):
    global socketio_instance
    socketio_instance = socketio



def on_message(client, userdata, msg, topic_name):
    try:
        data = json.loads(msg.payload)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON message from {topic_name}: {e}")
        return
    
    current_timestamp = datetime.now().strftime(timestamp_format)

    # Determine the table based on the topic
    table_name = f"device_data_{topic_name.replace('/', '_')}"

    print(f"Received data on {topic_name}: {data}")

    if isinstance(data, dict):
        data['timestamp'] = current_timestamp
        insert_data(table_name, data.get('param_id'), data.get('param_data'), data['timestamp'])

        # Emit real-time data through socketio_instance
        if socketio_instance:
            try:
                socketio_instance.emit(f'new_data_{topic_name.replace("/", "_")}', data)
            except Exception as e:
                print(f"Error emitting data through socket: {e}")
        else:
            print("SocketIO instance is not initialized.")

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                item['timestamp'] = current_timestamp
                insert_data(table_name, item.get('param_id'), item.get('param_data'), item['timestamp'])

                # Emit each item in the list as real-time data through socketio_instance
                if socketio_instance:
                    try:
                        socketio_instance.emit(f'new_data_{topic_name.replace("/", "_")}', item)
                    except Exception as e:
                        print(f"Error emitting data through socket: {e}")
                else:
                    print("SocketIO instance is not initialized.")


def start_mqtt_client(client_id, topic_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch the broker address for the topic from the database
    cursor.execute("""
        SELECT broker_address FROM mqtt_topics WHERE topic_name = ?
    """, (topics[topic_name],))
    broker_address = cursor.fetchone()['broker_address']
    
    conn.close()

    client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
    client.on_message = lambda client, userdata, msg: on_message(client, userdata, msg, topic_name)
    
    client.connect(broker_address)  # Use the dynamic broker address
    client.subscribe(topics[topic_name])
    
    client.loop_forever()

def start_new_topic_mqtt_client(topic_id, topic_name):
    if topic_name not in active_mqtt_clients:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT topic_name FROM mqtt_topics WHERE id = ?", (topic_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            topics[topic_name] = row['topic_name']
            thread = threading.Thread(target=start_mqtt_client, args=(f'IoT_Display_{topic_id}', topic_name))
            thread.daemon = True
            thread.start()
            active_mqtt_clients[topic_name] = thread


def start_threads():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, topic_name FROM mqtt_topics")
    topics_list = cursor.fetchall()

    for topic in topics_list:
        topic_id = f'topic{topic["id"]}'
        topics[topic_id] = topic["topic_name"]
        start_new_topic_mqtt_client(topic["id"], topic_id)

    conn.close()
