# Btrac EMS — IoT MQTT Monitoring Dashboard

This project is an end‑to‑end IoT monitoring dashboard built during the end of 2024 as an internship learning experience. It focuses on backend development, real‑time data handling, access control, and reporting for MQTT‑driven device telemetry.

Demo Accounts:
Username: usertest
Password: password123

Username: admin
Password: admin123

Username: multiple
Password: multiple123


## Highlights
- Real‑time charts over WebSockets using Flask‑SocketIO
- Per‑topic MQTT subscriber threads started dynamically
- Admin manages MQTT topics and devices; users get assigned access
- Historical charting with configurable time ranges (default: All Data)
- PDF and Excel export for summary and full datasets
- Granular access control for users and admins

## Architecture
- App entrypoint and Socket.IO setup: [app.py](file:///e:/Visual%20Studio/btrac_ems/app.py)
- Routes and pages (Blueprint): [routes.py](file:///e:/Visual%20Studio/btrac_ems/routes.py)
- MQTT ingestion and thread management: [mqtt_handlers.py](file:///e:/Visual%20Studio/btrac_ems/mqtt_handlers.py)
- Database helpers and access control: [database.py](file:///e:/Visual%20Studio/btrac_ems/database.py)
- PDF/Excel utilities: [utils.py](file:///e:/Visual%20Studio/btrac_ems/utils.py)
- Templates (UI): [templates](file:///e:/Visual%20Studio/btrac_ems/templates)
- Static assets (CSS): [static/css](file:///e:/Visual%20Studio/btrac_ems/static/css)

Data flow:
- MQTT messages arrive to topic‑specific clients, decoded and inserted into per‑topic tables.
- Socket.IO emits `new_data_topic{id}` events to live charts.
- Historical endpoints return filtered rows for chart rendering.

## Data Model
All data is stored in `mqtt_data.db` (SQLite). Key tables:
- `users` — id, username, email, password (hashed), is_admin
- `mqtt_topics` — id, topic_name, broker_address
- `devices` — id, device_name, mqtt_topic_id, device_location, device_type, organization, organogram
- `user_devices` — user_id, device_id, [high_threshold, low_threshold]
- `user_mqtt_topics` — id, user_id, mqtt_topic_id
- `admin_mqtt_topics` — admin_id, mqtt_topic_id
- `device_data_topic{id}` — id, param_id, param_data, timestamp

Access control:
- Admin access checked via `admin_mqtt_topics`
- User access checked via `user_mqtt_topics`
- See [user_has_access](file:///e:/Visual%20Studio/btrac_ems/database.py#L41-L66)

## Environment Variables
- `SECRET_KEY` or `FLASK_SECRET_KEY` — session secret (required for login)
- `WKHTMLTOPDF_PATH` — path to wkhtmltopdf executable for PDF export
  - Default: `C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe`
  - See [utils.py:_get_pdfkit_config](file:///e:/Visual%20Studio/btrac_ems/utils.py#L7-L13)
- `PARAM_MIN`, `PARAM_MAX` — optional numeric bounds to accept sensor values
  - If set, values outside `[PARAM_MIN, PARAM_MAX]` are skipped
  - See [insert_data](file:///e:/Visual%20Studio/btrac_ems/database.py#L12-L31)

## Setup
1. Ensure Python 3.11+ is installed.
2. Install dependencies:

```bash
pip install Flask Flask-SocketIO eventlet paho-mqtt Werkzeug pdfkit XlsxWriter
```

3. Install wkhtmltopdf (Windows):
   - Download from https://wkhtmltopdf.org/downloads.html
   - Set `WKHTMLTOPDF_PATH` to the installed `wkhtmltopdf.exe`

4. Create or verify the SQLite database file `mqtt_data.db` exists in the project root.

## Running
Start the server:

```bash
set SECRET_KEY=development
python app.py
```

Expected output:
- Running on `http://127.0.0.1:5000` and LAN address
- Subscriber threads start for each topic in `mqtt_topics`

## Admin Workflow
- Login as admin
- Add MQTT topic (creates `device_data_topic{id}` automatically)
- Create a device and link it to a topic
- Register users and assign devices (their topics are auto‑assigned)
- View data:
  - Single topic page: [index.html](file:///e:/Visual%20Studio/btrac_ems/templates/index.html) (default time range: All Data)
  - Multi‑chart page: [view_multiple_charts.html](file:///e:/Visual%20Studio/btrac_ems/templates/view_multiple_charts.html) (default time range: All Data)
- Download data:
  - Summary PDF: min/max/avg, trip length
  - Full PDF: graph with tabular data
  - Excel: timestamp and parameter data
  - Endpoint: [download_data](file:///e:/Visual%20Studio/btrac_ems/routes.py#L517)

## Real‑Time and Historical
- Event names: `new_data_topic{id}` emitted from MQTT handler
  - See [on_message](file:///e:/Visual%20Studio/btrac_ems/mqtt_handlers.py#L21-L61)
- Historical endpoints:
  - Single topic: `/load_data_topic<int:topic_id>?range=all|1|7|30|365`
    - See [load_data_topic](file:///e:/Visual%20Studio/btrac_ems/routes.py#L444-L514)
  - Multiple topics: `/load_multiple_data?topic_ids[]=...&range=all|1|7|30|365`
    - See [load_multiple_data](file:///e:/Visual%20Studio/btrac_ems/routes.py#L633-L684)
  - Default range is “all”

## Quick Test (Public Broker)
Seed a test topic and verify ingestion:

```bash
# Add test topic (id shown by last_insert_rowid())
sqlite3 mqtt_data.db "INSERT INTO mqtt_topics (topic_name, broker_address) VALUES ('trae/test/topic', 'test.mosquitto.org'); SELECT last_insert_rowid();"

# Create table if needed (replace 4 with your inserted id)
sqlite3 mqtt_data.db "CREATE TABLE IF NOT EXISTS device_data_topic4 (id INTEGER PRIMARY KEY AUTOINCREMENT, param_id TEXT NOT NULL, param_data REAL NOT NULL, timestamp TEXT NOT NULL);"

# Run the server in one terminal
set SECRET_KEY=development
python app.py

# Publish sample messages in another terminal
python publisher_test.py

# Verify rows
sqlite3 mqtt_data.db ".headers on" ".mode column" "SELECT COUNT(*) AS count FROM device_data_topic4;" "SELECT id, param_id, param_data, timestamp FROM device_data_topic4 ORDER BY id DESC LIMIT 5;"
```

You should see three rows inserted, then live updates on the chart via `new_data_topic4`.

To clear test data:

```bash
sqlite3 mqtt_data.db "DELETE FROM device_data_topic4;"
```

## Notes
- This codebase uses a modular Flask structure with Blueprints and separate MQTT/database/utils modules, aimed at maintainability and clarity for newcomers.
- Default chart view is “All Data” for both single‑topic and multi‑chart pages.

