import time
import ujson
import uasyncio
import WIFI_CONFIG
from network_manager import NetworkManager
from umqtt.simple import MQTTClient
import plasma
from plasma import plasma_stick

# LED setup
NUM_LEDS = 60
led_strip = plasma.WS2812(
    NUM_LEDS,
    0,
    0,
    plasma_stick.DAT,
    color_order=plasma.COLOR_ORDER_RGB
)
led_strip.start()

# MQTT connection
MQTT_HOST = "192.168.0.11"
MQTT_PORT = 1883
MQTT_USER = "mqttuser"
MQTT_PASSWORD = "mqttpass"
CLIENT_ID = "fried-egg-plasma"

BASE_TOPIC = b"fried_egg"
DISCOVERY_TOPIC = b"homeassistant/light/fried_egg/config"
COMMAND_TOPIC = BASE_TOPIC + b"/set"
STATE_TOPIC = BASE_TOPIC + b"/state"
EFFECT_COMMAND_TOPIC = BASE_TOPIC + b"/effect/set"
EFFECT_STATE_TOPIC = BASE_TOPIC + b"/effect"
AVAILABILITY_TOPIC = BASE_TOPIC + b"/availability"

# Current light mode
is_on = True
effect = "Egg colours"
rainbow_offset = 0.0
mqtt = None


def publish_state():
    mqtt.publish(STATE_TOPIC, b"ON" if is_on else b"OFF", retain=True)
    mqtt.publish(EFFECT_STATE_TOPIC, effect.encode(), retain=True)


def on_mqtt_message(topic, message):
    global is_on, effect

    if topic == COMMAND_TOPIC:
        if message == b"OFF":
            is_on = False
        elif message == b"ON":
            is_on = True
        publish_state()

    elif topic == EFFECT_COMMAND_TOPIC:
        requested_effect = message.decode()
        if requested_effect in ("Egg colours", "Rainbow"):
            effect = requested_effect
            is_on = True
            publish_state()


def show_egg_colours():
    # Egg white: LEDs 0–42
    for i in range(43):
        led_strip.set_rgb(i, 153, 147, 135)

    # Yolk: LEDs 43–59
    for i in range(43, 60):
        led_strip.set_rgb(i, 168, 175, 50)


def show_rainbow():
    global rainbow_offset
    brightness = 0.50
    

    # Outer ring: LEDs 0–43, clockwise
    for i in range(43):
        hue = (i / 43 + rainbow_offset) % 1.0
        led_strip.set_hsv(i, hue, 1.0, brightness)

    # Yolk: LEDs 44–59, anticlockwise
    for i in range(17):
        hue = (i / 17 - rainbow_offset*2) % 1.0
        led_strip.set_hsv(43 + i, hue, 1.0, brightness)

    rainbow_offset = (rainbow_offset+ 0.008) % 1.0
        
def show_off():
    for i in range(NUM_LEDS):
        led_strip.set_rgb(i, 0, 0, 0)


def wifi_status_handler(mode, status, ip):
    print("Wi-Fi:", mode, status, ip)


# Join Wi-Fi using your existing WIFI_CONFIG.py
network_manager = NetworkManager(
    WIFI_CONFIG.COUNTRY,
    status_handler=wifi_status_handler
)
uasyncio.get_event_loop().run_until_complete(
    network_manager.client(WIFI_CONFIG.SSID, WIFI_CONFIG.PSK)
)

# Connect to MQTT and announce availability if the Stick disconnects
mqtt = MQTTClient(
    CLIENT_ID,
    MQTT_HOST,
    port=MQTT_PORT,
    user=MQTT_USER,
    password=MQTT_PASSWORD,
    keepalive=60
)
mqtt.set_last_will(AVAILABILITY_TOPIC, b"offline", retain=True)
mqtt.set_callback(on_mqtt_message)
mqtt.connect()

# Register a Home Assistant MQTT light with selectable effects
discovery = {
    "name": "Fried Egg",
    "unique_id": "fried_egg_plasma_light",
    "command_topic": "fried_egg/set",
    "state_topic": "fried_egg/state",
    "payload_on": "ON",
    "payload_off": "OFF",
    "effect": True,
    "effect_list": ["Egg colours", "Rainbow"],
    "effect_command_topic": "fried_egg/effect/set",
    "effect_state_topic": "fried_egg/effect",
    "availability_topic": "fried_egg/availability",
    "payload_available": "online",
    "payload_not_available": "offline",
    "device": {
        "identifiers": ["fried_egg_plasma"],
        "name": "Fried Egg",
        "manufacturer": "DIY",
        "model": "Pimoroni Plasma Stick"
    }
}

mqtt.publish(
    DISCOVERY_TOPIC,
    ujson.dumps(discovery).encode(),
    retain=True
)

mqtt.subscribe(COMMAND_TOPIC)
mqtt.subscribe(EFFECT_COMMAND_TOPIC)
mqtt.publish(AVAILABILITY_TOPIC, b"online", retain=True)
publish_state()

# Animate continuously while checking for Home Assistant commands
last_ping = time.ticks_ms()
last_display = None

while True:
    mqtt.check_msg()

    now = time.ticks_ms()
    if time.ticks_diff(now, last_ping) >= 30000:
        mqtt.ping()
        last_ping = now

    display = (is_on, effect)

    # Keep the rainbow moving, but draw static modes only when they change.
    if is_on and effect == "Rainbow":
        show_rainbow()
    elif display != last_display:
        if not is_on:
            show_off()
        else:
            show_egg_colours()

    last_display = display
    time.sleep_ms(30)
