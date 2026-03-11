import paho.mqtt.client as mqtt

broker = "broker.hivemq.com"
port = 1883
topic = "school/temperature"

def on_message(client, userdata, msg):
    print("Received:", msg.payload.decode())

client = mqtt.Client()
client.on_message = on_message

client.connect(broker, port, keepalive=60)
client.subscribe(topic)

client.loop_forever()
