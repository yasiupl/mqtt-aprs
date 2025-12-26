# -*- coding: utf-8 -*-
import logging
import socket
import time
import json
import threading
import aprslib

class APRSClient:
    def __init__(self, config, mqtt_publisher_callback):
        self.config = config
        self.mqtt_publish = mqtt_publisher_callback
        self.aprs_is = None
        self._stop_event = threading.Event()

    def start_listener(self):
        """
        Start the background thread to listen to APRS-IS
        """
        if not self.config['APRS_IN_ENABLED']:
            logging.info("APRS Incoming Listener is disabled.")
            return

        if not self.config['APRS_IN_FILTER']:
            logging.warning("APRS Listener enabled but NO FILTER defined. This is dangerous!")
        
        t = threading.Thread(target=self._listener_loop)
        t.daemon = True
        t.start()

    def _listener_loop(self):
        while not self._stop_event.is_set():
            try:
                callsign = self.config['APRS_CALLSIGN']
                password = self.config['APRS_PASS']
                if not password:
                    password = "-1"
                    
                logging.info("Connecting to APRS-IS for incoming traffic...")
                self.aprs_is = aprslib.IS(callsign, passwd=password, host=self.config['APRS_SERVER'], port=self.config['APRS_PORT'])
                
                if self.config['APRS_IN_FILTER']:
                    self.aprs_is.set_filter(self.config['APRS_IN_FILTER'])
                
                self.aprs_is.connect()
                
                # Blocking call
                self.aprs_is.consumer(self._handle_packet, raw=False)
                
            except Exception as e:
                logging.error(f"APRS listener error: {e}")
                time.sleep(10) # Wait before reconnecting

    def _handle_packet(self, packet):
        # We only care about location packets
        if 'latitude' in packet and 'longitude' in packet:
            logging.debug(f"Received APRS packet from {packet.get('from')}")
            
            ot_data = self._aprs_to_owntracks(packet)
            if ot_data:
                # Topic: owntracks/aprs/CALLSIGN
                sender = packet.get('from')
                topic = f"{self.config['APRS_IN_TOPIC_PREFIX']}/{sender}"
                
                payload = json.dumps(ot_data)
                self.mqtt_publish(topic, payload)
                logging.debug(f"Published to {topic}: {payload}")

    def _aprs_to_owntracks(self, packet):
        """
        Convert parsed APRS packet to Owntracks JSON format
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

    def send_packet(self, packet):
        """
        Create a socket, log on to the APRS server, and send the packet
        """
        logging.debug(f"{self.config['APRS_SERVER']}:{self.config['APRS_PORT']}")
        try:
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.connect((self.config['APRS_SERVER'], self.config['APRS_PORT']))

            # Log on to APRS server
            auth = f'user {self.config["APRS_CALLSIGN"]} pass {self.config["APRS_PASS"]} vers "mqtt-zabbix" \n'
            connection.send(auth.encode('utf-8'))

            # Send APRS packet
            logging.debug(f"Sending {packet}")
            connection.send(packet.encode('utf-8'))
            logging.debug(f"Sent packet at: {time.ctime()}")

            # Close socket -- must be closed to avoidbuffer overflow
            time.sleep(2)  # Short delay to ensure send
            connection.shutdown(socket.SHUT_RDWR)
            connection.close()
        except Exception as e:
            logging.error(f"Failed to send packet: {str(e)}")
