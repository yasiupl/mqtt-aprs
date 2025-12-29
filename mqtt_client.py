# -*- coding: utf-8 -*-
import logging
import time
import json
import socket
import paho.mqtt.client as mqtt

class MQTTClient:
    """
    A client for handling interactions with the MQTT Broker.

    This class manages the MQTT connection, subscribes to configured topics,
    and publishes received messages to the broker. It handles generic message passing
    and does not perform protocol-specific conversions.
    """

    def __init__(self, config, message_handler_callback):
        """
        Initialize the MQTTClient.

        Args:
            config (dict): Application configuration dictionary containing MQTT settings.
            message_handler_callback (callable): Callback function to handle received messages.
                                             Signature: (message_payload)
        """
        self.config = config
        self.message_callback = message_handler_callback
        
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

        Parses JSON and passes it to the callback.
        The callback (main application) is responsible for processing logic.

        Args:
            msg (mqtt.MQTTMessage): The received message.
        """
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            if data.get('_type') == 'location':
                logging.debug(f"Received Owntracks location: {data}")
                self.message_callback(data)
            else:
                logging.debug("Not a location message")
        except Exception as e:
            logging.error(f"Failed to process message: {str(e)}")
