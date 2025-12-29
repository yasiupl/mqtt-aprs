# -*- coding: utf-8 -*-
import logging
import time
import json
import threading
import aprslib

class APRSClient:
    """
    A client for handling interactions with the APRS-IS network.
    
    This class manages the connection to an APRS-IS server, listens for incoming
    packets based on a filter, and sends outgoing packets. It acts as a transparent
    gateway for APRS traffic, passing received packets to a callback and sending
    packets provided via a method.
    """

    def __init__(self, config, packet_receiver_callback):
        """
        Initialize the APRSClient.

        Args:
            config (dict): Application configuration dictionary containing APRS settings.
            packet_receiver_callback (callable): Callback function to handle received packets.
        """
        self.config = config
        self.packet_callback = packet_receiver_callback
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
        Start the background thread to listen to APRS-IS for incoming traffic.
        
        If APRS_IN_ENABLED is false in the config, the listener is not started.
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
        """
        Main loop for the APRS listener thread.
        
        Maintains connection to APRS-IS and processes incoming packets.
        Auto-reconnects on failure.
        """
        while not self._stop_event.is_set():
            try:
                logging.info("Connecting to APRS-IS for incoming traffic...")
                
                if self.config['APRS_IN_FILTER']:
                    self.aprs_is.set_filter(self.config['APRS_IN_FILTER'])
                
                self.aprs_is.connect()
                
                # Blocking call - consumes packets indefinitely
                self.aprs_is.consumer(self._handle_packet, raw=False)
                
            except Exception as e:
                logging.error(f"APRS listener error: {e}")
                time.sleep(10) # Wait before reconnecting

    def _handle_packet(self, packet):
        """
        Callback handler for received APRS packets.

        Passes the raw packet to the callback for processing.

        Args:
            packet (dict): Parsed APRS packet data.
        """
        # We only care about location packets
        if 'latitude' in packet and 'longitude' in packet:
            logging.debug(f"Received APRS packet from {packet.get('from')}")
            
            # Pass raw packet to callback. Topic is handled by the callback (main app).
            self.packet_callback(None, packet)

    def send_packet(self, packet):
        """
        Send a raw APRS packet using the global aprslib instance.

        If the listener is running, it reuses the existing connection.
        Otherwise, it establishes a temporary connection for sending.

        Args:
            packet (str): Raw APRS packet string.
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
