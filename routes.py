from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from helpers import login_required
from database import get_db_connection, dict_factory, user_has_access
from utils import generate_pdf_summary, generate_excel, generate_pdf
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from mqtt_handlers import start_new_topic_mqtt_client
from datetime import datetime, timedelta


# Define the blueprint
app_routes = Blueprint('app_routes', __name__)

# User login route with error handling and session management
@app_routes.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            # Check if username and password are provided
            if not username or not password:
                flash('Username and password are required.', 'danger')
                return render_template('login.html')

            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
                user = cursor.fetchone()
            except sqlite3.OperationalError as e:
                flash('Database operation failed. Please try again later.', 'danger')
                print(f"Database error: {e}")  # Log the error for debugging
                return redirect(url_for('.apology'))

            if user:
                try:
                    # Check the hashed password
                    if check_password_hash(user['password'], password):
                        session['user_id'] = user['id']
                        session['username'] = user['username']
                        session['is_admin'] = user['is_admin']

                        if user['is_admin']:
                            conn.close()
                            return redirect(url_for('.home'))
                        else:
                            cursor.execute("""
                                SELECT m.id, m.topic_name
                                FROM mqtt_topics m
                                JOIN user_mqtt_topics umt ON m.id = umt.mqtt_topic_id
                                WHERE umt.user_id = ?
                            """, (user['id'],))
                            topics_assigned = cursor.fetchall()

                            if len(topics_assigned) > 1:
                                # If user has multiple topics, redirect to user dashboard
                                return redirect(url_for('.user_dashboard'))
                            elif len(topics_assigned) == 1:
                                # If only one topic, redirect directly to that topic's page
                                return redirect(url_for('.device_data', topic_id=topics_assigned[0]['id']))
                            else:
                                flash('No topics assigned. Contact your administrator.', 'danger')
                                return redirect(url_for('.login'))
                    else:
                        flash('Incorrect password. Please try again.', 'danger')
                except ValueError as e:
                    flash('An error occurred while verifying the password.', 'danger')
                    print(f"Password verification error: {e}")  # Log the error for debugging
                    return redirect(url_for('.apology'))
            else:
                flash('Username not found. Please try again.', 'danger')
        
        return render_template('login.html')

    except sqlite3.OperationalError as e:
        flash('Database operation failed. Please try again later.', 'danger')
        print(f"Operational error: {e}")  # Log the error for debugging
        return redirect(url_for('.apology'))

    except Exception as e:
        flash('An unexpected error occurred. Please try again later.', 'danger')
        print(f"Unexpected error: {e}")  # Log the error for debugging
        return redirect(url_for('.apology'))

    finally:
        # Ensure the connection is closed if it was opened
        if 'conn' in locals():
            conn.close()
                        
            
@app_routes.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('.login'))


@app_routes.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if not session.get('is_admin'):
        session.clear()
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        selected_devices = request.form.getlist('devices')  # Get selected devices

        # Validate that all fields are filled out
        if not email or not username or not password or not confirm_password:
            flash('All fields are required. Please fill out the form completely.', 'danger')
            cursor.execute("SELECT id, device_name FROM devices")
            devices = cursor.fetchall()
            conn.close()
            return render_template('register.html', devices=devices)

        # Validate that password and confirm_password match
        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            cursor.execute("SELECT id, device_name FROM devices")
            devices = cursor.fetchall()
            conn.close()
            return render_template('register.html', devices=devices)

        # Validate that at least one device is selected
        if not selected_devices:
            flash('At least one device must be selected.', 'danger')
            cursor.execute("SELECT id, device_name FROM devices")
            devices = cursor.fetchall()
            conn.close()
            return render_template('register.html', devices=devices)

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        try:
            # Insert the new user with the hashed password
            cursor.execute("""
                INSERT INTO users (username, email, password, is_admin)
                VALUES (?, ?, ?, 0)
            """, (username, email, hashed_password))
            user_id = cursor.lastrowid

            # Assign selected devices to the user
            for device_id in selected_devices:
                # Insert the device into the user_devices table
                cursor.execute("""
                    INSERT INTO user_devices (user_id, device_id)
                    VALUES (?, ?)
                """, (user_id, device_id))

                # Fetch the mqtt_topic_id from the device
                cursor.execute("""
                    SELECT mqtt_topic_id FROM devices WHERE id = ?
                """, (device_id,))
                mqtt_topic_id = cursor.fetchone()['mqtt_topic_id']

                # Insert the associated MQTT topic into the user_mqtt_topics table
                cursor.execute("""
                    INSERT INTO user_mqtt_topics (user_id, mqtt_topic_id)
                    VALUES (?, ?)
                """, (user_id, mqtt_topic_id))

            conn.commit()
            flash(f'User {username} registered successfully and assigned devices and MQTT topics.', 'success')
            return redirect(url_for('.home'))

        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                flash('Username or email already exists. Please try a different one.', 'danger')
            else:
                flash('An error occurred during registration. Please try again.', 'danger')

        except Exception as e:
            conn.rollback()
            flash('An unexpected error occurred. Please try again.', 'danger')
            print(f"Error: {e}")  # Log the error for debugging purposes

        finally:
            conn.close()

    # Fetch all available devices to display in the registration form
    cursor.execute("SELECT id, device_name FROM devices")
    devices = cursor.fetchall()
    conn.close()

    return render_template('register.html', devices=devices)

@app_routes.route('/')
@login_required
def home():
    if session.get('is_admin'):
        try:
            conn = get_db_connection()
            conn.row_factory = dict_factory
            cursor = conn.cursor()

            # Fetch all MQTT topics
            cursor.execute("SELECT id, topic_name FROM mqtt_topics")
            topics = cursor.fetchall()

            # Fetch all devices with their associated organization and organogram
            cursor.execute("""
                SELECT d.id AS device_id, d.device_name, d.device_location, 
                       d.device_type, d.organization, d.organogram, 
                       m.topic_name, m.id AS topic_id 
                FROM devices d
                JOIN mqtt_topics m ON d.mqtt_topic_id = m.id
            """)
            devices = cursor.fetchall()

            # Organize data by organization and organogram
            organizations = {}
            for device in devices:
                org = device['organization']
                orgo = device['organogram']
                if org not in organizations:
                    organizations[org] = {}
                if orgo not in organizations[org]:
                    organizations[org][orgo] = []
                organizations[org][orgo].append(device)

            conn.close()

            # Render the template with the topics, devices, organizations, and organograms
            return render_template('home.html', 
                                   topics=topics, 
                                   devices=devices, 
                                   organizations=organizations
                                   )
        except Exception as e:
            flash('An error occurred while loading the data. Please try again later.', 'danger')
            print(f"Error: {e}")
            return redirect(url_for('.apology'))
    else:
        session.clear()
        flash('Unauthorized access. Admins only.', 'danger')
        return redirect(url_for('.login'))


@app_routes.route('/user_dashboard', methods=['GET', 'POST'])
@login_required
def user_dashboard():
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()


    # Fetch devices and their associated thresholds for the logged-in user
    cursor.execute("""
        SELECT d.id AS device_id, d.device_name, m.id AS topic_id, m.topic_name, 
               ud.high_threshold, ud.low_threshold
        FROM devices d
        JOIN mqtt_topics m ON d.mqtt_topic_id = m.id
        JOIN user_devices ud ON d.id = ud.device_id
        WHERE ud.user_id = ?
    """, (user_id,))
    
    user_devices = cursor.fetchall()
    conn.close()

    if not user_devices:
        flash('No devices assigned. Contact your administrator.', 'danger')
        return redirect(url_for('.logout'))

    return render_template('user_dashboard.html', devices=user_devices)


@app_routes.route('/add_topic', methods=['GET', 'POST'])
@login_required
def add_topic():
    if not session.get('is_admin'):
        session.clear()
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('.login'))

    if request.method == 'POST':
        topic_name = request.form['topic_name']
        broker_address = request.form['broker_address']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Insert the new topic into mqtt_topics table (device details removed)
            cursor.execute("""
                INSERT INTO mqtt_topics (topic_name, broker_address)
                VALUES (?, ?)
            """, (topic_name, broker_address))
            conn.commit()

            # Get the last inserted id from mqtt_topics
            topic_id = cursor.lastrowid

            # Generate the table name using the topic_id
            table_name = f'device_data_topic{topic_id}'

            # Create the new table with the generated table name
            cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    param_id TEXT NOT NULL,
                    param_data REAL NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()
            
            # Add admin access to the new topic in admin_mqtt_topics
            admin_id = session['user_id']  # Assuming the admin is the one who is logged in
            cursor.execute("""
                INSERT INTO admin_mqtt_topics (admin_id, mqtt_topic_id)
                VALUES (?, ?)
            """, (admin_id, topic_id))
            conn.commit()

            # Start a new MQTT client thread for the new topic
            start_new_topic_mqtt_client(topic_id, f'topic{topic_id}')
            
            flash(f'MQTT topic "{topic_name}" added successfully.', 'success')
            return redirect(url_for('.home'))
        except sqlite3.IntegrityError:
            conn.rollback()
            flash('Topic name already exists. Please try a different one.', 'danger')
        finally:
            conn.close()

    return render_template('add_topic.html')

@app_routes.route('/create_device', methods=['GET', 'POST'])
@login_required
def create_device():
    if not session.get('is_admin'):
        session.clear()
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('.login'))

    if request.method == 'POST':
        device_name = request.form['device_name']
        device_location = request.form['device_location']
        device_type = request.form['device_type']
        organization = request.form['organization']
        organogram = request.form['organogram']
        mqtt_topic_id = request.form['mqtt_topic_id']  # Selected MQTT topic

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Insert the new device into the devices table, linking it to the selected MQTT topic
            cursor.execute("""
                INSERT INTO devices (device_name, mqtt_topic_id, device_location, device_type, organization, organogram)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device_name, mqtt_topic_id, device_location, device_type, organization, organogram))
            conn.commit()

            flash(f'Device "{device_name}" created and assigned to MQTT topic successfully.', 'success')
            return redirect(url_for('.home'))
        except sqlite3.IntegrityError:
            conn.rollback()
            flash('Device name already exists. Please try a different one.', 'danger')
        finally:
            conn.close()

    # Fetch all available MQTT topics to allow the admin to assign a topic to a device
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, topic_name FROM mqtt_topics")
    topics = cursor.fetchall()
    conn.close()

    return render_template('create_device.html', topics=topics)


# Route to serve the device data page dynamically based on the topic
@app_routes.route('/topic/<int:topic_id>')
@login_required
def device_data(topic_id):
    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch the topic and associated device details
    cursor.execute("""
        SELECT m.topic_name, d.device_location, d.device_type, d.device_name
        FROM mqtt_topics m
        JOIN devices d ON m.id = d.mqtt_topic_id
        WHERE m.id = ?
    """, (topic_id,))
    
    topic = cursor.fetchone()

    # Fetch the current user information
    cursor.execute("""
        SELECT u.username, u.email
        FROM users u
        WHERE u.id = ?
    """, (user_id,))
    
    user = cursor.fetchone()

    conn.close()

    if not topic:
        flash('Topic not found.', 'danger')
        return redirect(url_for('.home'))

    # Check if the user has access to the topic
    if user_has_access(user_id, topic['topic_name']):
        return render_template(
            'index.html', 
            topic_id=topic_id, 
            topic_name=topic['topic_name'],
            device_location=topic['device_location'], 
            device_type=topic['device_type'],
            device_name=topic['device_name'],
            username=user['username'],  
            email=user['email']
        )
    else:
        flash('You are not authorized to view this page.', 'danger')
        return redirect(url_for('.login'))

@app_routes.route('/apology')
def apology():
    return render_template("apology.html")

# Route to load historical data for topic with optional time filter
@app_routes.route('/load_data_topic<int:topic_id>')
@login_required
def load_data_topic(topic_id):
    user_id = session.get('user_id')

    # Get the selected time range from the query parameter
    time_range = request.args.get('range', 'all')

    # Determine the time range for the SQL query
    time_limit = None
    if time_range == '1':  # Last 24 hours
        time_limit = datetime.now() - timedelta(days=1)
    elif time_range == '7':  # Last 7 days
        time_limit = datetime.now() - timedelta(days=7)
    elif time_range == '30':  # Last 30 days
        time_limit = datetime.now() - timedelta(days=30)
    elif time_range == '365':  # Last 365 days
        time_limit = datetime.now() - timedelta(days=365)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Admins can access any topic
    if session.get('is_admin'):
        cursor.execute("SELECT topic_name FROM mqtt_topics WHERE id = ?", (topic_id,))
    else:
        cursor.execute("""
            SELECT m.topic_name 
            FROM mqtt_topics m 
            JOIN user_mqtt_topics umt ON m.id = umt.mqtt_topic_id 
            WHERE umt.user_id = ? AND m.id = ?
        """, (user_id, topic_id))
    
    topic = cursor.fetchone()
    conn.close()
    
    if topic:
        table_name = f'device_data_topic{topic_id}'
        
        if session.get('is_admin') or user_has_access(user_id, topic['topic_name']):
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                query = f"SELECT param_data, timestamp FROM {table_name}"
                params = ()

                # If a specific time range is selected, add the condition to the query
                if time_limit:
                    query += " WHERE timestamp >= ?"
                    params = (time_limit.strftime('%Y-%m-%d %H:%M:%S'),)

                query += " ORDER BY timestamp ASC"
                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()

                # Format the data
                data = [{'param_data': row[0], 'timestamp': row[1]} for row in rows]
                return jsonify(data)

            except sqlite3.Error as e:
                print(f"Database error: {e}")
                flash('An error occurred while retrieving the data.', 'danger')
                return redirect(url_for('.login'))
        else:
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('.login'))
    else:
        flash('Topic not found or access denied.', 'danger')
        return redirect(url_for('.login'))


@app_routes.route('/download_data', methods=['GET', 'POST'])
@login_required
def download_data():
    if not session.get('is_admin'):
        flash('Unauthorized access. Admins only.', 'danger')
        return redirect(url_for('.login'))
    conn = get_db_connection()  # Open connection once at the start
    cursor = conn.cursor()

    # Fetch all topics from the database to populate the dropdown
    cursor.execute("SELECT id, topic_name FROM mqtt_topics")
    topics = cursor.fetchall()

    if request.method == 'POST':
        topic_id = request.form['topic_id']
        start_date_str = request.form['start_date']  # Original start date string
        end_date_str = request.form['end_date']      # Original end date string
        format_type = request.form['format_type']
        download_type = request.form['download_type']

        # Handle date formatting if time is missing (default to '00:00:00' for start and '23:59:59' for end)
        if len(start_date_str) == 10:  # Only date part provided, e.g., '2024-10-02'
            start_date_str += ' 00:00:00'  # Default to the start of the day
        if len(end_date_str) == 10:
            end_date_str += ' 23:59:59'  # Default to the end of the day

        # Parse start_date and end_date into datetime objects
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M:%S')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
        except ValueError as e:
            flash(f'Error parsing date: {e}', 'danger')
            return render_template('download.html', topics=topics)

        # Function to format timedelta for trip length
        def format_timedelta(td: timedelta):
            total_seconds = int(td.total_seconds())
            days, remainder = divmod(total_seconds, 86400)  # 86400 seconds in a day
            hours, remainder = divmod(remainder, 3600)  # 3600 seconds in an hour
            minutes, seconds = divmod(remainder, 60)  # 60 seconds in a minute
            return f"{days:02}d {hours:02}h {minutes:02}m {seconds:02}s"

        # Calculate trip length
        trip_length = format_timedelta(end_date - start_date)

        # Fetch data from the database
        query = f"""
            SELECT param_data, timestamp FROM device_data_topic{topic_id}
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """
        cursor.execute(query, (start_date_str, end_date_str))
        rows = cursor.fetchall()

        # Check if any data is returned
        if not rows:
            flash('No data available for the selected time range.', 'danger')
            conn.close()  # Close the connection here
            return render_template('download.html', topics=topics)

        # Fetch the device name and type
        cursor.execute("""
            SELECT d.device_name, d.device_type
            FROM devices d
            JOIN mqtt_topics m ON d.mqtt_topic_id = m.id
            WHERE m.id = ?
        """, (topic_id,))
        device_info = cursor.fetchone()
        device_name = device_info['device_name']
        device_type = device_info['device_type']

        # Fetch the MQTT topic name for labeling PDFs
        cursor.execute("SELECT topic_name FROM mqtt_topics WHERE id = ?", (topic_id,))
        topic_row = cursor.fetchone()
        topic_name = topic_row['topic_name'] if topic_row else f'topic{topic_id}'

        # Summary dictionary with all necessary fields
        summary = {
            'min': min(row[0] for row in rows),
            'max': max(row[0] for row in rows),
            'avg': sum(row[0] for row in rows) / len(rows),
            'trip_length': trip_length,  # Corrected trip length
            'data_count': len(rows),
            'file_created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # If download type is summary, return the PDF summary
        if download_type == 'summary':
            if format_type == 'pdf':
                conn.close()  # Close the connection before returning
                return generate_pdf_summary(summary, device_name, device_type, start_date_str, end_date_str)

        # Full data PDF or Excel generation logic
        elif download_type == 'full_data':
            if format_type == 'pdf':
                conn.close()  # Close the connection before returning
                return generate_pdf(rows, topic_name, start_date_str, end_date_str)
            elif format_type == 'excel':
                conn.close()  # Close the connection before returning
                return generate_excel(rows)

    conn.close()  # Ensure connection is closed at the end
    return render_template('download.html', topics=topics)

@app_routes.route('/view_multiple_charts', methods=['GET', 'POST'])
@login_required
def view_multiple_charts():
    # Fetch topics from the database for the dropdown
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, topic_name FROM mqtt_topics")
    topics = cursor.fetchall()
    conn.close()

    return render_template('view_multiple_charts.html', topics=topics)


@app_routes.route('/load_multiple_data')
@login_required
def load_multiple_data():
    user_id = session.get('user_id')
    topic_ids = request.args.getlist('topic_ids[]')
    time_range = request.args.get('range', 'all')

    if not topic_ids:
        return jsonify({'error': 'No topics selected'}), 400

    time_limit = None
    if time_range == '1':  # Last 24 hours
        time_limit = datetime.now() - timedelta(days=1)
    elif time_range == '7':  # Last 7 days
        time_limit = datetime.now() - timedelta(days=7)
    elif time_range == '30':  # Last 30 days
        time_limit = datetime.now() - timedelta(days=30)
    elif time_range == '365':  # Last 365 days
        time_limit = datetime.now() - timedelta(days=365)

    conn = get_db_connection()
    cursor = conn.cursor()
    data = {}

    for topic_id in topic_ids:
        table_name = f'device_data_topic{topic_id}'
        # Enforce access control: admins can access all; users must have explicit access
        if not session.get('is_admin'):
            conn_access = get_db_connection()
            cur_access = conn_access.cursor()
            cur_access.execute("SELECT topic_name FROM mqtt_topics WHERE id = ?", (topic_id,))
            t = cur_access.fetchone()
            conn_access.close()
            if not t or not user_has_access(user_id, t['topic_name']):
                continue

        query = f"SELECT param_data, timestamp FROM {table_name}"
        params = ()

        if time_limit:
            query += " WHERE timestamp >= ?"
            params = (time_limit.strftime('%Y-%m-%d %H:%M:%S'),)

        query += " ORDER BY timestamp ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        data[f'topic_{topic_id}'] = [{'param_data': row[0], 'timestamp': row[1]} for row in rows]

    conn.close()
    return jsonify(data)
