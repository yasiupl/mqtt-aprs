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
import json

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
    
    Sets up logging level, format, and optional file output.
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
        """
        Callback for MQTT Client to send an APRS packet.

        This function handles the conversion of Owntracks data to APRS
        if necessary, or passes raw APRS strings directly.

        Args:
            packet (dict or str): The payload to send. Can be an Owntracks
                                  dictionary or a raw APRS packet string.
        """
        if aprs_client:
            # Check if packet is a dictionary (Owntracks format) and convert to APRS string
            if isinstance(packet, dict):
                aprs_string = owntracks_to_aprs(packet)
                if aprs_string:
                    aprs_client.send_packet(aprs_string)
            else:
                # Assume it's already a raw APRS packet string
                aprs_client.send_packet(packet)
            
    # Wrapper for MQTT Client to publish (passed to APRS Client)
    def mqtt_publish(topic, payload):
        """
        Callback for APRS Client to publish to MQTT.

        This function handles the conversion of APRS packet data to Owntracks JSON
        if necessary, or passes raw topic/payload pairs directly.

        Args:
            topic (str or None): The MQTT topic. If payload is a dict (raw APRS),
                                 this is ignored/calculated.
            payload (dict or str): The payload to publish. Can be a raw APRS packet
                                   dictionary or a ready-to-send string.
        """
        if mqtt_client:
            # Check if payload is a dict (raw APRS packet data) and convert to Owntracks JSON
            if isinstance(payload, dict):
                ot_data = aprs_to_owntracks(payload)
                if ot_data:
                    # Construct topic based on sender
                    sender = payload.get('from', 'UNKNOWN')
                    topic = f"{CONFIG['APRS_IN_TOPIC_PREFIX']}/{sender}"
                    
                    json_payload = json.dumps(ot_data)
                    mqtt_client.publish(topic, json_payload)
            else:
                # Assume it's already fully formed topic and payload
                mqtt_client.publish(topic, payload)

    def aprs_to_owntracks(packet):
        """
        Convert a parsed APRS packet to Owntracks JSON format.

        Args:
            packet (dict): Parsed APRS packet dictionary.

        Returns:
            dict: Owntracks JSON payload or None if conversion failed.
        """
        try:
            # Basic Owntracks payload
            ot_payload = {
                "_type": "location",
                "lat": packet.get('latitude'),
                "lon": packet.get('longitude'),
                "tst": int(packet.get('timestamp', time.time())),
                "tid": packet.get('from', '')[:2] # Tracker ID (2 chars)
            }

            # Optional fields
            if 'altitude' in packet:
                ot_payload['alt'] = int(packet['altitude'])
            
            if 'speed' in packet:
                ot_payload['vel'] = int(packet['speed'])
                
            if 'course' in packet:
                ot_payload['cog'] = int(packet['course'])

            return ot_payload
        except Exception as e:
            logging.error(f"Error converting APRS to Owntracks: {e}")
            return None

    def owntracks_to_aprs(data):
        """
        Convert Owntracks JSON format to an APRS packet string.

        Args:
            data (dict): Owntracks JSON payload.

        Returns:
            str: Raw APRS packet string or None if conversion failed or not a location message.
        """
        try:
            if data.get('_type') == 'location':
                address = f"{CONFIG['APRS_CALLSIGN']}-{CONFIG['APRS_SSID']}>APRS,TCPIP*:"
                lat = _deg_to_dms(float(data['lat']), 0)
                lon = _deg_to_dms(float(data['lon']), 1)
                position = f"={lat}{CONFIG['APRS_TABL']}{lon}{CONFIG['APRS_SYMB']}"

                packet = f"{address}{position} mqtt-aprs\n"
                return packet
            else:
                logging.debug("Not a location message")
                return None
        except Exception as e:
            logging.error(f"Failed to convert Owntracks to APRS: {str(e)}")
            return None

    def _deg_to_dms(deg, long_flag):
        """
        Convert decimal degrees to APRS Degrees Minutes Seconds (DMS) format.

        Args:
            deg (float): Decimal degrees.
            long_flag (int): 0 for latitude, 1 for longitude.

        Returns:
            str: APRS formatted DMS string.
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
