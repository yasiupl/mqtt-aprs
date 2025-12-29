#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT-APRS Gateway

This application acts as a bi-directional gateway between the APRS-IS network and an MQTT broker.
It relays location updates from APRS to Owntracks-compatible MQTT topics and vice-versa.
"""

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
    """
    Load configuration from the specified CFG file.

    Populates the global CONFIG dictionary.

    Args:
        path (str): Path to the configuration file. Defaults to /etc/mqtt-aprs/mqtt-aprs.cfg.
                    Falls back to local 'mqtt-aprs.cfg' if the default path doesn't exist.
    """
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
        """Helper to safely get config values with type conversion."""
        try:
            if is_bool: return config.getboolean(section, option)
            if is_int: return config.getint(section, option)
            return config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    # Global settings
    CONFIG["DEBUG"] = get("global", "DEBUG", default=False, is_bool=True)
    CONFIG["LOGFILE"] = get("global", "LOGFILE")
    
    # MQTT settings
    CONFIG["MQTT_HOST"] = get("mqtt", "HOST", default="localhost")
    CONFIG["MQTT_PORT"] = get("mqtt", "PORT", default=1883, is_int=True)
    CONFIG["MQTT_USER"] = get("mqtt", "USER")
    CONFIG["MQTT_PASS"] = get("mqtt", "PASS")
    CONFIG["MQTT_OUT_ENABLED"] = get("mqtt_outgoing", "ENABLED", default=True, is_bool=True)
    CONFIG["MQTT_TOPIC"] = get("mqtt_outgoing", "TOPIC", default="owntracks/+/+")
    
    # APRS settings
    CONFIG["APRS_SERVER"] = get("aprs", "SERVER", default="rotate.aprs2.net")
    CONFIG["APRS_PORT"] = get("aprs", "PORT", default=14580, is_int=True)
    CONFIG["APRS_CALLSIGN"] = get("aprs", "CALLSIGN", default="N0CALL")
    CONFIG["APRS_SSID"] = get("aprs", "SSID", default="0")
    CONFIG["APRS_PASS"] = get("aprs", "PASS", default="-1")
    CONFIG["APRS_SYMB"] = get("aprs", "SYMBOL", default="[")
    CONFIG["APRS_TABL"] = get("aprs", "TABLE", default="/")
    
    # APRS Incoming settings
    CONFIG["APRS_IN_ENABLED"] = get("aprs_incoming", "ENABLED", default=False, is_bool=True)
    CONFIG["APRS_IN_FILTER"] = get("aprs_incoming", "FILTER")
    CONFIG["APRS_IN_TOPIC_PREFIX"] = get("aprs_incoming", "TOPIC_PREFIX", default="owntracks/aprs")

def setup_logging():
    """
    Configure the logging system based on the loaded configuration.
    """
    log_format = "%(asctime)-15s %(message)s"
    level = logging.DEBUG if CONFIG.get("DEBUG") else logging.INFO
    
    kwargs = {'level': level, 'format': log_format}
    if CONFIG.get("LOGFILE"):
        kwargs['filename'] = CONFIG["LOGFILE"]
        
    logging.basicConfig(**kwargs)
    logging.info(f"Starting {APPNAME}")
    logging.info(f"Debug mode: {CONFIG.get('DEBUG')}")

def main():
    """
    Main application entry point.
    
    Initializes configuration, logging, and starts the MQTT and APRS clients.
    """
    setproctitle.setproctitle(APPNAME)
    load_config()
    setup_logging()

    # --- Initialization ---
    
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
