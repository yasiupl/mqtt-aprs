# mqtt-aprs

A bidirectional bridge between **MQTT** (specifically [Owntracks](https://owntracks.org/) JSON format) and the **APRS-IS** network.

This daemon allows you to:
1.  **Relay Owntracks locations to APRS**: Listen for MQTT messages from Owntracks and post them to the APRS network as your station's location.
2.  **Bridge APRS traffic to MQTT**: Connect to APRS-IS, filter for specific packets (e.g., within a geographic range or specific callsigns), convert them to Owntracks JSON format, and publish them to your MQTT broker.

## Features

*   **Python 3**: Modernized codebase using `paho-mqtt` and `aprslib`.
*   **Bidirectional**: Supports both sending to and receiving from APRS-IS.
*   **Filtering**: Configurable server-side filters for incoming APRS traffic to prevent flooding your broker.
*   **Docker Support**: Includes a `Dockerfile` and `docker-compose.yml` for easy deployment.
*   **Owntracks Compatible**: Converts APRS locations into standard Owntracks JSON payloads (`_type: location`).

## Prerequisites

*   Python 3.8+
*   An MQTT Broker (e.g., Mosquitto)
*   An APRS-IS Passcode (required for sending data to APRS, but optional for receiving only)

## Installation

### Option 1: Docker (Recommended)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/kylegordon/mqtt-aprs.git
    cd mqtt-aprs
    ```

2.  **Configuration:**
    Copy the example configuration and edit it with your details.
    ```bash
    cp mqtt-aprs.cfg.example mqtt-aprs.cfg
    nano mqtt-aprs.cfg
    ```
    *See the [Configuration](#configuration) section for details on settings.*

3.  **Run with Docker Compose:**
    ```bash
    docker-compose up -d
    ```

### Option 2: Manual Installation

1.  **Install system dependencies:**
    (Example for Debian/Ubuntu)
    ```bash
    sudo apt-get install python3 python3-pip git
    ```

2.  **Clone the repository:**
    ```bash
    git clone https://github.com/kylegordon/mqtt-aprs.git
    cd mqtt-aprs
    ```

3.  **Set up a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

4.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configuration:**
    ```bash
    cp mqtt-aprs.cfg.example mqtt-aprs.cfg
    nano mqtt-aprs.cfg
    ```

6.  **Run the application:**
    ```bash
    python3 mqtt-aprs.py
    ```

## Configuration

Configuration is managed via `mqtt-aprs.cfg`.

### `[global]`
*   `DEBUG`: Set to `True` for verbose logging.
*   `LOGFILE`: Optional path to a log file. If omitted, logs to stdout.

### `[mqtt]`
*   `HOST`, `PORT`, `USER`, `PASS`: Connection details for your MQTT broker.

### `[aprs]`
*   `SERVER`: APRS-IS server (default `rotate.aprs2.net`).
*   `CALLSIGN`: Your amateur radio callsign.
*   `SSID`: Your SSID (e.g., `9` for mobile, `0` for home).
*   `PASS`: Your APRS-IS passcode. Required if you want to transmit to APRS.
*   `SYMBOL`, `TABLE`: The APRS symbol to use when reporting your location.

### `[mqtt_outgoing]` (Owntracks -> APRS)
*   `ENABLED`: Set to `True` to enable this direction.
*   `TOPIC`: The MQTT topic to listen to for your Owntracks updates (e.g., `owntracks/myuser/myphone`).

### `[aprs_incoming]` (APRS -> MQTT)
*   `ENABLED`: Set to `True` to enable this direction.
*   `FILTER`: **Critical setting**. Defines which packets to receive from the global APRS network.
    *   **Range Filter**: `r/52.2/21.0/50` (50km radius around Warsaw)
    *   **Prefix Filter**: `p/N0CALL` (Only packets from N0CALL)
    *   *See [APRS-IS Filters](http://www.aprs-is.net/javAPRSFilter.aspx) for more options.*
*   `TOPIC_PREFIX`: The prefix for published MQTT messages. Packets will be published to: `<TOPIC_PREFIX>/<CALLSIGN>`.
    *   Example: If prefix is `owntracks/aprs`, a packet from `N0CALL` will be published to `owntracks/aprs/N0CALL`.

## License

See LICENSE file for details.
