# -*- coding: utf-8 -*-
import logging
import time
import json
import socket
import paho.mqtt.client as mqtt

class MQTTClient:
    """
    A client for handling interactions with the MQTT Broker.

    This class manages the MQTT connection, subscribes to Owntracks location topics,
    and publishes received APRS packets to the broker. It also handles the conversion
    of Owntracks JSON payloads to APRS packet format.
    """

    def __init__(self, config, aprs_sender_callback):
        """
        Initialize the MQTTClient.

        Args:
            config (dict): Application configuration dictionary containing MQTT settings.
            aprs_sender_callback (callable): Callback function to send APRS packets.
                                             Signature: (packet_string)
        """
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
        """
        Connect to the MQTT Broker.

        Raises:
            Exception: If connection fails.
        """
        try:
            logging.debug(f"Connecting to {self.config['MQTT_HOST']}:{self.config['MQTT_PORT']}")
            self.client.connect(self.config['MQTT_HOST'], self.config['MQTT_PORT'], 60)
        except Exception as e:
            logging.critical(f"Could not connect to MQTT Broker: {e}")
            raise e

    def start(self):
        """
        Start the MQTT client loop in a background thread.
        """
        self.client.loop_start()

    def stop(self):
        """
        Stop the MQTT client.
        
        Publishes a "0" to the presence topic, stops the loop, and disconnects.
        """
        self.client.publish(self.presence_topic, "0", retain=True)
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic, payload):
        """
        Publish a message to an MQTT topic.

        Args:
            topic (str): The MQTT topic.
            payload (str): The message payload.
        """
        self.client.publish(topic, payload)

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback when the client connects to the broker.

        Handles subscription setup and presence notification.
        """
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
        """
        Callback when the client disconnects from the broker.
        """
        if rc == 0:
            logging.info("Clean disconnection")
        else:
            logging.info(f"Unexpected disconnection! RC: {rc}")

    def _on_message(self, client, userdata, msg):
        """
        Callback when a message is received from the broker.

        Delegates processing to _process_message.
        """
        logging.debug(f"Received: {str(msg.payload)} on {msg.topic}")
        self._process_message(msg)

    def _on_log(self, client, userdata, level, string):
        """
        Callback for MQTT client logging.
        """
        logging.debug(string)

    def _process_message(self, msg):
        """
        Process an incoming MQTT message.

        Parses Owntracks JSON, converts coordinates to APRS format,
        constructs an APRS packet, and sends it via the callback.

        Args:
            msg (mqtt.MQTTMessage): The received message.
        """
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
        Convert decimal degrees to APRS Degrees Minutes Seconds (DMS) format.

        Args:
            deg (float): Coordinate in decimal degrees.
            long_flag (bool): True if longitude (3-digit degrees), False if latitude (2-digit degrees).

        Returns:
            str: Formatted DMS string (e.g., "5130.00N" or "00005.00W").
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
