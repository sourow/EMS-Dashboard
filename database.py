import sqlite3
import os
from flask import session
database_name = 'mqtt_data.db'

def get_db_connection():
    conn = sqlite3.connect(database_name)
    conn.row_factory = sqlite3.Row
    return conn


def insert_data(table_name, param_id, param_data, timestamp):
    min_val = os.environ.get('PARAM_MIN')
    max_val = os.environ.get('PARAM_MAX')
    if min_val is not None and max_val is not None:
        try:
            min_v = float(min_val)
            max_v = float(max_val)
            if not (min_v <= float(param_data) <= max_v):
                print(f"Skipping data insertion. Value {param_data} is outside the range {min_v} to {max_v}")
                return
        except Exception:
            pass

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(f'''INSERT INTO {table_name} (param_id, param_data, timestamp)
                    VALUES (?, ?, ?)''', (param_id, param_data, timestamp))
    conn.commit()
    conn.close()


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}

def dict_factory(cursor, row):
    """Converts the row output to a dictionary-like format"""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def user_has_access(user_id, topic_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    if session.get('is_admin'):
        # Admins should have access to all topics
        cursor.execute("""
            SELECT 1
            FROM mqtt_topics m
            JOIN admin_mqtt_topics amt ON m.id = amt.mqtt_topic_id
            WHERE amt.admin_id = ? AND m.topic_name = ?
        """, (user_id, topic_name))
    else:
        # Check if the regular user has access to the topic
        cursor.execute("""
            SELECT 1
            FROM mqtt_topics m
            JOIN user_mqtt_topics umt ON m.id = umt.mqtt_topic_id
            WHERE umt.user_id = ? AND m.topic_name = ?
        """, (user_id, topic_name))

    result = cursor.fetchone()
    conn.close()
    
    return result is not None

def get_device_details_by_topic_id(topic_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT device_name, device_type
        FROM devices
        WHERE mqtt_topic_id = ?
    """, (topic_id,))
    device_details = cursor.fetchone()
    conn.close()

    return {'device_name': device_details[0], 'device_type': device_details[1]} if device_details else {'device_name': 'Unknown', 'device_type': 'Unknown'}
