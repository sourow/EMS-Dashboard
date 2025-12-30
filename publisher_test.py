import json
import time
import paho.mqtt.client as mqtt

BROKER = 'test.mosquitto.org'
PORT = 1883
TOPIC = 'trae/test/topic'

def main():
    client = mqtt.Client(client_id='TraePublisherTest', protocol=mqtt.MQTTv311)
    client.connect(BROKER, PORT, keepalive=60)
    payload1 = json.dumps({'param_id': 'temp', 'param_data': 24.6})
    client.publish(TOPIC, payload=payload1, qos=0, retain=False)
    time.sleep(1)
    payload2 = json.dumps([
        {'param_id': 'temp', 'param_data': 25.1},
        {'param_id': 'temp', 'param_data': 25.3}
    ])
    client.publish(TOPIC, payload=payload2, qos=0, retain=False)
    time.sleep(1)
    client.disconnect()

if __name__ == '__main__':
    main()