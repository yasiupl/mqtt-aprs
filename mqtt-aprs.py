#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import signal
import logging
import configparser
import setproctitle

from mqtt_client import MQTTClient
from aprs_client import APRSClient

__author__ = "Marcin Jasiukowicz (based on original work by Kyle Gordon)"
__copyright__ = "Copyright (C) Marcin Jasiukowicz"

APPNAME = "mqtt-aprs"

# Global Config Dictionary
CONFIG = {}

def load_config(path="/etc/mqtt-aprs/mqtt-aprs.cfg"):
    config = configparser.ConfigParser()
    if not os.path.exists(path):
        # Fallback for development if file is local
        if os.path.exists("mqtt-aprs.cfg"):
            path = "mqtt-aprs.cfg"
        else:
            logging.warning(f"Config file {path} not found.")
            return

    config.read(path)

    def get(section, option, default=None, is_bool=False, is_int=False):
        try:
            if is_bool: return config.getboolean(section, option)
            if is_int: return config.getint(section, option)
            return config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    CONFIG["DEBUG"] = get("global", "DEBUG", default=False, is_bool=True)
    CONFIG["LOGFILE"] = get("global", "LOGFILE")
    
    CONFIG["MQTT_HOST"] = get("mqtt", "HOST", default="localhost")
    CONFIG["MQTT_PORT"] = get("mqtt", "PORT", default=1883, is_int=True)
    CONFIG["MQTT_USER"] = get("mqtt", "USER")
    CONFIG["MQTT_PASS"] = get("mqtt", "PASS")
    CONFIG["MQTT_OUT_ENABLED"] = get("mqtt_outgoing", "ENABLED", default=True, is_bool=True)
    CONFIG["MQTT_TOPIC"] = get("mqtt_outgoing", "TOPIC", default="owntracks/+/+")
    
    CONFIG["APRS_SERVER"] = get("aprs", "SERVER", default="rotate.aprs2.net")
    CONFIG["APRS_PORT"] = get("aprs", "PORT", default=14580, is_int=True)
    CONFIG["APRS_CALLSIGN"] = get("aprs", "CALLSIGN", default="N0CALL")
    CONFIG["APRS_SSID"] = get("aprs", "SSID", default="0")
    CONFIG["APRS_PASS"] = get("aprs", "PASS", default="-1")
    CONFIG["APRS_SYMB"] = get("aprs", "SYMBOL", default="[")
    CONFIG["APRS_TABL"] = get("aprs", "TABLE", default="/")
    
    CONFIG["APRS_IN_ENABLED"] = get("aprs_incoming", "ENABLED", default=False, is_bool=True)
    CONFIG["APRS_IN_FILTER"] = get("aprs_incoming", "FILTER")
    CONFIG["APRS_IN_TOPIC_PREFIX"] = get("aprs_incoming", "TOPIC_PREFIX", default="owntracks/aprs")

def setup_logging():
    log_format = "%(asctime)-15s %(message)s"
    level = logging.DEBUG if CONFIG.get("DEBUG") else logging.INFO
    
    kwargs = {'level': level, 'format': log_format}
    if CONFIG.get("LOGFILE"):
        kwargs['filename'] = CONFIG["LOGFILE"]
        
    logging.basicConfig(**kwargs)
    logging.info(f"Starting {APPNAME}")
    logging.info(f"Debug mode: {CONFIG.get('DEBUG')}")

def main():
    setproctitle.setproctitle(APPNAME)
    load_config()
    setup_logging()

    # --- Initialization ---
    
    # We need a way to pass callbacks between the two clients
    # MQTT Client needs to send packets to APRS
    # APRS Client needs to publish messages to MQTT
    
    # Deferred initialization pattern or wrapper needed?
    # Simple approach: Create instances, then wire them up or pass wrappers.
    
    # Wrapper for APRS Client to send packet (passed to MQTT Client)
    def send_aprs_packet(packet):
        if aprs_client:
            aprs_client.send_packet(packet)
            
    # Wrapper for MQTT Client to publish (passed to APRS Client)
    def mqtt_publish(topic, payload):
        if mqtt_client:
            mqtt_client.publish(topic, payload)

    # Initialize Clients
    global mqtt_client, aprs_client
    
    aprs_client = APRSClient(CONFIG, mqtt_publish)
    mqtt_client = MQTTClient(CONFIG, send_aprs_packet)
    
    # Connect and Start
    try:
        mqtt_client.connect()
        mqtt_client.start() # Starts loop in background thread
        
        aprs_client.start_listener() # Starts loop in background thread
        
        # Main thread just waits for signals
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logging.info("Interrupted by keypress")
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
    finally:
        logging.info("Shutting down...")
        if mqtt_client: mqtt_client.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()
