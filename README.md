# IoT-Based Home Security Monitoring System

## Project Overview

This project presents the design and implementation of an IoT-based home security monitoring system. The system detects potential hazards in a residential environment and transmits sensor data in real time using the MQTT communication protocol.

The solution integrates Arduino-based hardware, MQTT messaging, a Python backend, and an SQLite database to create a functional monitoring prototype.

## Project Methodology

The project was developed using the Agile methodology. Agile was selected due to its flexibility, adaptability, and support for continuous improvement. It allows modifications during development, coding, and testing stages while maintaining system stability.

The iterative approach enabled gradual integration of hardware components, MQTT communication, and backend data processing. Continuous refinement ensured improved reliability and efficient system performance.

## Project Components

The system consists of the following components:

**Hardware**

- Arduino Uno microcontroller
- Solu SL067 Water Level Sensor
- KY-026 Flame Sensor Module
- LDR Light Sensor Module (LM393-based)
- MQ-6 Gas Sensor
- Scaled physical room prototype for testing

**Software**

- Python MQTT subscriber (`subscriber.py`)
- MQTT-to-database integration script (`MQTT to SQLIte.py`)
- SQLite database (`smarthome_security.db`)

**MQTT Configuration**

- Broker: `broker.hivemq.com`
- Port: `1883`
- Topic structure: `smarthome/security/sensors/#`

**Arduino UNO sensor monitoring system**

Sensors:

- Flame sensor (A0)
- Gas sensor (A1)
- Water sensor (A2)
- Light sensor (Digital pin 2)

The system outputs sensor values in JSON format every 2 seconds via Serial.

**1. Data Encryption**

Sensor data transmitted via MQTT is secured using lightweight encryption techniques to ensure privacy and prevent unauthorized access. The encryption module processes JSON payloads before publishing to the MQTT broker, maintaining data integrity and confidentiality in real-time communications.

**2. Data Visualization with Python**

A Python-based visualization module was developed to provide real-time graphical representation of sensor readings. The module subscribes to MQTT topics, retrieves sensor data, and displays interactive charts using libraries such as Matplotlib and Plotly. This allows users to monitor environmental conditions, detect anomalies, and respond to potential hazards efficiently.

**3. Mobile Application (Java)**

A Java-based application was implemented to interface with the IoT monitoring system. The application provides the following:

- Real-time display of sensor readings
- Alerts for abnormal sensor values (e.g., fire, gas leak, water overflow)
- User-friendly graphical interface for enhanced usability

The application communicates with the Python backend via MQTT, ensuring seamless integration between hardware, backend, and front-end interfaces.

# Application Interface and Visualization

## MQTT Connection Control

The application interface includes two main buttons:

- **Connect**
- **Disconnect**

These buttons control the connection to the MQTT broker.

- The **Connect** button establishes a connection between the application and the MQTT broker.
- The **Disconnect** button terminates the connection.

This allows the user to manually control when the application communicates with the MQTT system.

## Sensor Indicators

Below the connection controls, the application displays **sensor indicators** that show the values received from the Arduino device.

The indicators represent data collected from the sensors connected to the Arduino and transmitted through MQTT.

Each sensor value is categorized into one of three status levels depending on the value received:

- **Good** – the environment is safe and sensor values are within the normal range.
- **Problem** – the sensor detects unusual values that may indicate a potential issue.
- **Emergency** – the sensor value exceeds the safety threshold and may indicate a dangerous situation.

## Data Visualization

A Python script performs the following steps:

1. Retrieves sensor data from the **SQLite database**.
2. Processes the collected data.
3. Generates a **graph representing the sensor readings over time**.
4. Encodes the generated graph as an image.

After encoding the image, the Python script **publishes the graph image via MQTT**. The application then receives this image and displays the **visualized sensor data graph** to the user.

## System Summary

Environmental data is collected by sensors connected to the Arduino Uno. The data is published via MQTT and received by a Python-based subscriber. Sensor readings are processed and stored in an SQLite database with timestamps.

The project demonstrates how IoT technologies, lightweight messaging protocols, and database systems can be integrated to build a functional home security monitoring prototype.

## Authors

Developed as a group academic project. Individual contributions are documented in the final project report.
