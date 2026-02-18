package com.example.homesecurity;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import com.hivemq.client.mqtt.MqttClient;
import com.hivemq.client.mqtt.mqtt3.Mqtt3AsyncClient;
import com.hivemq.client.mqtt.mqtt3.message.publish.Mqtt3Publish;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";
    private static final String CHANNEL_ID = "emergency_alerts";
    private static final int NOTIFICATION_PERMISSION_CODE = 100;

    private Mqtt3AsyncClient mqttClient;

    private TextView statusText;
    private TextView flameText;
    private TextView gasText;
    private TextView waterText;
    private TextView lightText;
    private Button connectButton;
    private Button disconnectButton;

    private final String brokerHost = "broker.hivemq.com";
    private final int brokerPort = 1883;
    private final String baseTopic = "smarthome/security/sensors/";

    // Track last emergency state to avoid spam notifications
    private boolean lastFlameEmergency = false;
    private boolean lastGasEmergency = false;
    private boolean lastWaterEmergency = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        connectButton = findViewById(R.id.connectButton);
        disconnectButton = findViewById(R.id.disconnectButton);
        statusText = findViewById(R.id.statusText);
        flameText = findViewById(R.id.flameText);
        gasText = findViewById(R.id.gasText);
        waterText = findViewById(R.id.waterText);
        lightText = findViewById(R.id.lightText);

        connectButton.setOnClickListener(v -> connectMqtt());
        disconnectButton.setOnClickListener(v -> disconnectMqtt());

        // Create notification channel and request permission
        createNotificationChannel();
        requestNotificationPermission();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            CharSequence name = "Emergency Alerts";
            String description = "Critical security alerts for fire, gas, and water leaks";
            int importance = NotificationManager.IMPORTANCE_HIGH;
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, name, importance);
            channel.setDescription(description);
            channel.enableVibration(true);
            channel.enableLights(true);
            channel.setLightColor(Color.RED);

            NotificationManager notificationManager = getSystemService(NotificationManager.class);
            notificationManager.createNotificationChannel(channel);
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.POST_NOTIFICATIONS},
                        NOTIFICATION_PERMISSION_CODE);
            }
        }
    }

    private void sendEmergencyNotification(String title, String message, int notificationId) {
        // Check permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                Log.w(TAG, "Notification permission not granted");
                return;
            }
        }

        Intent intent = new Intent(this, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        PendingIntent pendingIntent = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_alert)
                .setContentTitle(title)
                .setContentText(message)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .setVibrate(new long[]{0, 500, 200, 500})
                .setDefaults(NotificationCompat.DEFAULT_SOUND | NotificationCompat.DEFAULT_LIGHTS);

        NotificationManagerCompat notificationManager = NotificationManagerCompat.from(this);
        notificationManager.notify(notificationId, builder.build());
    }

    private void connectMqtt() {
        runOnUiThread(() -> {
            statusText.setText("Connecting...");
            statusText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
            connectButton.setEnabled(false);
        });

        new Thread(() -> {
            try {
                mqttClient = MqttClient.builder()
                        .useMqttVersion3()
                        .identifier("AndroidApp_" + UUID.randomUUID().toString().substring(0, 8))
                        .serverHost(brokerHost)
                        .serverPort(brokerPort)
                        .buildAsync();

                Log.d(TAG, "Connecting to MQTT broker...");

                mqttClient.connectWith()
                        .send()
                        .whenComplete((connAck, throwable) -> {
                            if (throwable != null) {
                                Log.e(TAG, "Connection failed", throwable);
                                runOnUiThread(() -> {
                                    statusText.setText("Connection failed ✗");
                                    statusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                                    connectButton.setEnabled(true);
                                    disconnectButton.setEnabled(false);
                                    Toast.makeText(this, "Failed: " + throwable.getMessage(),
                                            Toast.LENGTH_LONG).show();
                                });
                            } else {
                                Log.d(TAG, "Connected successfully!");
                                runOnUiThread(() -> {
                                    statusText.setText("Connected ✓");
                                    statusText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
                                    connectButton.setEnabled(false);
                                    disconnectButton.setEnabled(true);
                                    Toast.makeText(this, "Connected to MQTT!",
                                            Toast.LENGTH_SHORT).show();
                                });

                                subscribeToTopics();
                            }
                        });

            } catch (Exception e) {
                Log.e(TAG, "Error creating MQTT client", e);
                runOnUiThread(() -> {
                    statusText.setText("Error: " + e.getMessage());
                    statusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                    connectButton.setEnabled(true);
                    disconnectButton.setEnabled(false);
                });
            }
        }).start();
    }

    private void disconnectMqtt() {
        if (mqttClient != null && mqttClient.getState().isConnected()) {
            mqttClient.disconnect().whenComplete((v, throwable) -> {
                runOnUiThread(() -> {
                    statusText.setText("Disconnected");
                    statusText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    connectButton.setEnabled(true);
                    disconnectButton.setEnabled(false);

                    // Reset all sensor displays
                    flameText.setText("Waiting...");
                    flameText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    gasText.setText("Waiting...");
                    gasText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    waterText.setText("Waiting...");
                    waterText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    lightText.setText("Waiting...");
                    lightText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));

                    // Reset emergency states
                    lastFlameEmergency = false;
                    lastGasEmergency = false;
                    lastWaterEmergency = false;

                    Toast.makeText(this, "Disconnected from MQTT", Toast.LENGTH_SHORT).show();
                });
            });
        }
    }

    private void subscribeToTopics() {
        mqttClient.subscribeWith()
                .topicFilter(baseTopic + "#")
                .callback(this::handleMessage)
                .send()
                .whenComplete((subAck, throwable) -> {
                    if (throwable != null) {
                        Log.e(TAG, "Subscribe failed", throwable);
                    } else {
                        Log.d(TAG, "Subscribed to: " + baseTopic + "#");
                        runOnUiThread(() ->
                                Toast.makeText(this, "Listening for sensor data...",
                                        Toast.LENGTH_SHORT).show()
                        );
                    }
                });
    }

    private void handleMessage(Mqtt3Publish publish) {
        String topic = publish.getTopic().toString();
        String message = new String(publish.getPayloadAsBytes(), StandardCharsets.UTF_8);

        Log.d(TAG, "Message received - Topic: " + topic + ", Message: " + message);

        runOnUiThread(() -> {
            if (topic.endsWith("flame")) {
                updateFlameStatus(message);
            } else if (topic.endsWith("gas")) {
                updateGasStatus(message);
            } else if (topic.endsWith("water")) {
                updateWaterStatus(message);
            } else if (topic.endsWith("light")) {
                updateLightStatus(message);
            }
        });
    }

    // FLAME SENSOR: Higher values (near 1000) = Good, Lower values = Fire detected
    private void updateFlameStatus(String value) {
        try {
            int numValue = Integer.parseInt(value.trim());

            if (numValue >= 800) {
                flameText.setText("Good");
                flameText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
                lastFlameEmergency = false;
            } else if (numValue >= 400 && numValue < 800) {
                flameText.setText("Heat Detected");
                flameText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
                lastFlameEmergency = false;
            } else if (numValue < 400) {
                flameText.setText("FIRE DETECTED!");
                flameText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));

                // Send notification only if this is a new emergency
                if (!lastFlameEmergency) {
                    sendEmergencyNotification(
                            "🔥 FIRE DETECTED!",
                            "Flame sensor detected fire! Check your home immediately!",
                            1
                    );
                    lastFlameEmergency = true;
                }
            }
        } catch (NumberFormatException e) {
            flameText.setText("Error: " + value);
            flameText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
        }
    }

    // GAS SENSOR: Lower values (≤150) = Good, Higher values (near 1000) = Gas leak
    private void updateGasStatus(String value) {
        try {
            int numValue = Integer.parseInt(value.trim());

            if (numValue <= 150) {
                gasText.setText("Good");
                gasText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
                lastGasEmergency = false;
            } else if (numValue > 150 && numValue <= 500) {
                gasText.setText("Minor Leak");
                gasText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
                lastGasEmergency = false;
            } else if (numValue > 500) {
                gasText.setText("GAS LEAK!");
                gasText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));

                // Send notification only if this is a new emergency
                if (!lastGasEmergency) {
                    sendEmergencyNotification(
                            "💨 GAS LEAK DETECTED!",
                            "Dangerous gas levels detected! Evacuate and ventilate immediately!",
                            2
                    );
                    lastGasEmergency = true;
                }
            }
        } catch (NumberFormatException e) {
            gasText.setText("Error: " + value);
            gasText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
        }
    }

    // WATER SENSOR: Lower values = Good, Higher values (near 1000) = Water detected
    private void updateWaterStatus(String value) {
        try {
            int numValue = Integer.parseInt(value.trim());

            if (numValue <= 100) {
                waterText.setText("Good");
                waterText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
                lastWaterEmergency = false;
            } else if (numValue > 100 && numValue <= 400) {
                waterText.setText("Minor Leakage");
                waterText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
                lastWaterEmergency = false;
            } else if (numValue > 400) {
                waterText.setText("WATER LEAK!");
                waterText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));

                // Send notification only if this is a new emergency
                if (!lastWaterEmergency) {
                    sendEmergencyNotification(
                            "💧 WATER LEAK DETECTED!",
                            "Water leak detected! Check for flooding immediately!",
                            3
                    );
                    lastWaterEmergency = true;
                }
            }
        } catch (NumberFormatException e) {
            waterText.setText("Error: " + value);
            waterText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
        }
    }

    // LIGHT SENSOR: 0 = On (green), 1 = Off (red)
    private void updateLightStatus(String value) {
        try {
            int numValue = Integer.parseInt(value.trim());

            if (numValue == 0) {
                lightText.setText("On");
                lightText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
            } else if (numValue == 1) {
                lightText.setText("Off");
                lightText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
            } else {
                lightText.setText("Unknown: " + value);
                lightText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
            }
        } catch (NumberFormatException e) {
            lightText.setText("Error: " + value);
            lightText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (mqttClient != null && mqttClient.getState().isConnected()) {
            mqttClient.disconnect();
            Log.d(TAG, "Disconnected from MQTT");
        }
    }
}