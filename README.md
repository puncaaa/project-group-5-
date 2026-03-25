# IoT-Based Home Security Monitoring System

## Project Overview
This project presents the design and implementation of an IoT-based home security monitoring system. The system detects potential hazards in a residential environment and transmits sensor data in real time using the MQTT communication protocol.

The solution integrates Arduino-based hardware, MQTT messaging, a Python backend, and an SQLite database to create a functional monitoring prototype.

## Project Methodology
The project was developed using the Agile methodology. Agile was selected due to its flexibility, adaptability, and support for continuous improvement. It allows modifications during development, coding, and testing stages while maintaining system stability.

The iterative approach enabled gradual integration of hardware components, MQTT communication, and backend data processing. Continuous refinement ensured improved reliability and efficient system performance.

## Project Components

### Hardware
- Arduino Uno microcontroller  
- Solu SL067 Water Level Sensor  
- KY-026 Flame Sensor Module  
- LDR Light Sensor Module (LM393-based)  
- MQ-6 Gas Sensor  
- Scaled physical room prototype for testing  

### Software
- Python MQTT subscriber (subscriber.py)  
- MQTT-to-database integration script (MQTT to SQLite.py)  
- SQLite database (smarthome_security.db)  

## MQTT Configuration
- Broker: broker.hivemq.com  
- Port: 8883 (TLS)  
- Topic structure: smarthome/security/sensors/#  

## Arduino UNO Sensor Monitoring System

### Sensors
- Flame sensor (A0)  
- Gas sensor (A1)  
- Water sensor (A2)  
- Light sensor (Digital pin 2)  

The system outputs sensor values in JSON format every 2 seconds via Serial.

## 1. Data Encryption
Sensor data transmitted via MQTT is secured using AES-256-GCM encryption to ensure privacy and prevent unauthorised access. The encryption module processes JSON payloads before publishing to the MQTT broker, maintaining data integrity and confidentiality in real-time communications. Each message uses a freshly generated random 16-byte nonce, with the wire format structured as:

Base64(nonce[16] + ciphertext[N] + tag[16])

## 2. Data Visualisation with Python
A Python-based visualisation module was developed to provide real-time graphical representation of sensor readings. The module subscribes to MQTT topics, retrieves sensor data from the SQLite database, and serves aggregated chart data over MQTT upon request. This allows users to monitor environmental conditions, detect anomalies, and respond to potential hazards efficiently.

## 3. Tkinter Dashboard
A Python-based desktop dashboard was implemented using Tkinter to interface with the IoT monitoring system. The dashboard provides the following:

- Real-time display of sensor readings received via MQTT  
- Visual status indicators for each sensor (Good, Problem, Emergency)  
- Alerts for abnormal sensor values (e.g., fire, gas leak, water overflow)  
- Historical data analysis through an interactive chart view  
- Manual MQTT connection control via Connect and Disconnect buttons  

The dashboard communicates with the Python backend via MQTT, ensuring seamless integration between hardware, backend, and the graphical interface. It is launched via run_dashboard.py and relies on the chart service being active for the analysis tab to function.

## Application Interface and Visualisation

### MQTT Connection Control
The dashboard interface includes two main buttons:

- Connect – establishes a connection between the dashboard and the MQTT broker  
- Disconnect – terminates the connection  

These buttons allow the user to manually control when the dashboard communicates with the MQTT system.

### Sensor Indicators
Below the connection controls, the dashboard displays sensor indicators that show the values received from the Arduino device. Each sensor value is categorised into one of three status levels:

- Good – the environment is safe and sensor values are within the normal range  
- Problem – the sensor detects unusual values that may indicate a potential issue  
- Emergency – the sensor value exceeds the safety threshold and may indicate a dangerous situation  

### Data Visualisation
The dashboard includes an Analysis tab that requests chart data from the chart service over MQTT. The chart service performs the following steps:

1. Retrieves aggregated sensor data from the SQLite database  
2. Processes and packages the collected data  
3. Encrypts and publishes the chart data as JSON over MQTT  
4. The dashboard receives the response and renders the visualised sensor readings  

A configurable timeout (CHART_TIMEOUT_SEC, default 15 seconds) is applied when awaiting chart data. The user may retry if the request times out.

## System Summary
Environmental data is collected by sensors connected to the Arduino Uno. The data is published via MQTT and received by a Python-based subscriber. Sensor readings are processed and stored in an SQLite database with timestamps. The Tkinter dashboard provides a live view of sensor statuses and historical chart analysis, communicating with dedicated backend services through encrypted MQTT messages.

The project demonstrates how IoT technologies, lightweight messaging protocols, encryption, and database systems can be integrated to build a functional home security monitoring prototype.

## Authors
Developed as a group academic project. Individual contributions are documented in the final project report.
