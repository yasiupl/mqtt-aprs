# -*- coding: utf-8 -*-
import logging
import time
import json
import socket
import paho.mqtt.client as mqtt

class MQTTClient:
    def __init__(self, config, aprs_sender_callback):
        self.config = config
        self.aprs_send = aprs_sender_callback
        
        self.appname = "mqtt-aprs" # Could be passed in
        self.presence_topic = f"clients/{socket.getfqdn()}/{self.appname}/state"
        
        # Initialize MQTT Client
        client_id = f"{self.appname}_{int(time.time())}"
        self.client = mqtt.Client(client_id=client_id)
        
        if self.config['MQTT_USER'] and self.config['MQTT_PASS']:
            self.client.username_pw_set(self.config['MQTT_USER'], self.config['MQTT_PASS'])
            
        self.client.will_set(self.presence_topic, "0", qos=0, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        if self.config['DEBUG']:
            self.client.on_log = self._on_log

    def connect(self):
        try:
            logging.debug(f"Connecting to {self.config['MQTT_HOST']}:{self.config['MQTT_PORT']}")
            self.client.connect(self.config['MQTT_HOST'], self.config['MQTT_PORT'], 60)
        except Exception as e:
            logging.critical(f"Could not connect to MQTT Broker: {e}")
            raise e

    def start(self):
        self.client.loop_start()

    def stop(self):
        self.client.publish(self.presence_topic, "0", retain=True)
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic, payload):
        self.client.publish(topic, payload)

    def _on_connect(self, client, userdata, flags, rc):
        logging.debug(f"on_connect RC: {rc}")
        if rc == 0:
            logging.info(f"Connected to {self.config['MQTT_HOST']}:{self.config['MQTT_PORT']}")
            client.publish(self.presence_topic, "1", retain=True)
            
            if self.config.get('MQTT_OUT_ENABLED', True):
                client.subscribe(self.config['MQTT_TOPIC'])
                logging.info(f"Subscribed to {self.config['MQTT_TOPIC']}")
            else:
                logging.info("MQTT Outgoing (subscription) is disabled.")
        else:
            logging.warning(f"Connection failed/refused with RC: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc == 0:
            logging.info("Clean disconnection")
        else:
            logging.info(f"Unexpected disconnection! RC: {rc}")

    def _on_message(self, client, userdata, msg):
        logging.debug(f"Received: {str(msg.payload)} on {msg.topic}")
        self._process_message(msg)

    def _on_log(self, client, userdata, level, string):
        logging.debug(string)

    def _process_message(self, msg):
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            if data.get('_type') == 'location':
                address = f"{self.config['APRS_CALLSIGN']}-{self.config['APRS_SSID']}>APRS,TCPIP*:"
                lat = self._deg_to_dms(float(data['lat']), 0)
                lon = self._deg_to_dms(float(data['lon']), 1)
                position = f"={lat}{self.config['APRS_TABL']}{lon}{self.config['APRS_SYMB']}"

                packet = f"{address}{position} {self.appname}\n"
                logging.debug(f"Packet is {packet}")
                self.aprs_send(packet)
            else:
                logging.debug("Not a location message")
        except Exception as e:
            logging.error(f"Failed to process message: {str(e)}")

    def _deg_to_dms(self, deg, long_flag):
        """
        Convert degrees to degrees, minutes and seconds
        """
        d = int(deg)
        md = round(abs(deg - d) * 60, 2)
        m = int(md)
        hm = int((md - m) * 100)

        if long_flag:
            suffix = "E" if d > 0 else "W"
            # APRS longitude is 3 digits for degrees
            aprsdms = f"{str(d).strip('-').zfill(3)}{str(m).zfill(2)}.{str(hm).zfill(2)}{suffix}"
        else:
            suffix = "N" if d > 0 else "S"
            # APRS latitude is 2 digits for degrees
            aprsdms = f"{str(d).strip('-').zfill(2)}{str(m).zfill(2)}.{str(hm).zfill(2)}{suffix}"
            
        return aprsdms
