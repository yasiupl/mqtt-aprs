# -*- coding: utf-8 -*-
import logging
import time
import json
import threading
import aprslib

class APRSClient:
    def __init__(self, config, mqtt_publisher_callback):
        self.config = config
        self.mqtt_publish = mqtt_publisher_callback
        self._stop_event = threading.Event()
        
        # Initialize global aprslib instance
        password = self.config['APRS_PASS']
        if not password:
            password = "-1"
            
        self.aprs_is = aprslib.IS(
            self.config['APRS_CALLSIGN'], 
            passwd=password, 
            host=self.config['APRS_SERVER'], 
            port=self.config['APRS_PORT']
        )

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
                logging.info("Connecting to APRS-IS for incoming traffic...")
                
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
        Send packet using the global aprslib instance
        """
        logging.debug(f"Sending packet via aprslib: {packet.strip()}")
        try:
            if self.config['APRS_IN_ENABLED']:
                # Reuse existing connection from the listener
                # Note: This relies on thread-safety of the underlying socket for send vs recv
                try:
                    self.aprs_is.sendall(packet)
                    logging.debug(f"Sent packet via existing listener connection at: {time.ctime()}")
                except Exception as e:
                    logging.warning(f"Failed to send via listener connection: {e}")
                    # We do not attempt to reconnect here as the listener loop handles lifecycle
            else:
                # Establish a temporary connection since listener is disabled
                logging.debug("Connecting to APRS-IS (outbound only)...")
                try:
                    self.aprs_is.connect()
                    self.aprs_is.sendall(packet)
                    logging.debug(f"Sent packet via new connection at: {time.ctime()}")
                finally:
                    # Always close the temporary connection
                    try:
                        self.aprs_is.close()
                    except Exception:
                        pass
                        
        except Exception as e:
            logging.error(f"Failed to send packet: {str(e)}")
