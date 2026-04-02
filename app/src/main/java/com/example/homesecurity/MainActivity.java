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
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.ProgressBar;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import com.github.mikephil.charting.charts.LineChart;
import com.github.mikephil.charting.components.XAxis;
import com.github.mikephil.charting.components.YAxis;
import com.github.mikephil.charting.data.Entry;
import com.github.mikephil.charting.data.LineData;
import com.github.mikephil.charting.data.LineDataSet;
import com.hivemq.client.mqtt.MqttClient;
import com.hivemq.client.mqtt.mqtt3.Mqtt3AsyncClient;
import com.hivemq.client.mqtt.mqtt3.message.publish.Mqtt3Publish;

import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.json.JSONArray;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.Security;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";
    private static final String CHANNEL_ID = "emergency_alerts";
    private static final int NOTIFICATION_PERMISSION_CODE = 100;
    private static final int CHART_LOAD_TIMEOUT_MS = 15000; // 15 seconds

    private static final String AES_KEY_HEX = "dd75fc2d686e27a660a25fb5dfa94910e0e9bb4a40f3fe8e89178f93b5de2222";
    private static final int GCM_TAG_LENGTH = 128;

    private Mqtt3AsyncClient realtimeMqttClient;
    private Mqtt3AsyncClient chartMqttClient;

    // UI Components - Realtime
    private ScrollView realtimeView;
    private TextView statusText;
    private TextView flameText, gasText, waterText, lightText;
    private Button connectButton, disconnectButton;
    private Button realtimeTab, analysisTab;

    // UI Components - Analysis
    private ScrollView analysisView;
    private RadioGroup timeRangeGroup;
    private Button loadChartsButton;
    private ProgressBar chartLoadingProgress;
    private TextView chartStatusText;
    private LineChart flameChart, gasChart, waterChart;

    private final String brokerHost = "broker.hivemq.com";
    private final int brokerPort = 8883;
    private final String realtimeTopic = "smarthome/security/sensors/";
    private final String chartRequestTopic = "smarthome/security/charts/request";
    private final String chartResponseTopic = "smarthome/security/charts/response";

    private boolean lastFlameEmergency = false;
    private boolean lastGasEmergency = false;
    private boolean lastWaterEmergency = false;

    private boolean isRealtimeView = true;
    private boolean isConnected = false;
    private String selectedTimeRange = "24h";

    private Handler chartTimeoutHandler = new Handler(Looper.getMainLooper());
    private Runnable chartTimeoutRunnable;
    private int chartsLoaded = 0;

    static {
        Security.removeProvider("BC");
        Security.addProvider(new BouncyCastleProvider());
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        initializeViews();
        setupCharts();
        setupListeners();
        createNotificationChannel();
        requestNotificationPermission();
        updateConnectionState(false);
    }

    private void initializeViews() {
        realtimeTab = findViewById(R.id.realtimeTab);
        analysisTab = findViewById(R.id.analysisTab);

        realtimeView = findViewById(R.id.realtimeView);
        analysisView = findViewById(R.id.analysisView);

        statusText = findViewById(R.id.statusText);
        flameText = findViewById(R.id.flameText);
        gasText = findViewById(R.id.gasText);
        waterText = findViewById(R.id.waterText);
        lightText = findViewById(R.id.lightText);
        connectButton = findViewById(R.id.connectButton);
        disconnectButton = findViewById(R.id.disconnectButton);

        timeRangeGroup = findViewById(R.id.timeRangeGroup);
        loadChartsButton = findViewById(R.id.loadChartsButton);
        chartLoadingProgress = findViewById(R.id.chartLoadingProgress);
        chartStatusText = findViewById(R.id.chartStatusText);
        flameChart = findViewById(R.id.flameChart);
        gasChart = findViewById(R.id.gasChart);
        waterChart = findViewById(R.id.waterChart);
    }

    private void setupCharts() {
        setupChart(flameChart, "Flame", Color.rgb(244, 67, 54));
        setupChart(gasChart, "Gas", Color.rgb(255, 193, 7));
        setupChart(waterChart, "Water", Color.rgb(33, 150, 243));
    }

    private void setupChart(LineChart chart, String label, int color) {
        chart.getDescription().setEnabled(false);
        chart.setTouchEnabled(true);
        chart.setDragEnabled(true);
        chart.setScaleEnabled(true);
        chart.setPinchZoom(true);
        chart.setDrawGridBackground(false);

        XAxis xAxis = chart.getXAxis();
        xAxis.setPosition(XAxis.XAxisPosition.BOTTOM);
        xAxis.setDrawGridLines(false);
        xAxis.setTextColor(getResources().getColor(R.color.status_info, getTheme()));

        YAxis leftAxis = chart.getAxisLeft();
        leftAxis.setDrawGridLines(true);
        leftAxis.setAxisMinimum(0f);
        leftAxis.setTextColor(getResources().getColor(R.color.status_info, getTheme()));

        chart.getAxisRight().setEnabled(false);
        chart.getLegend().setEnabled(false);

        chart.setNoDataText("Connect and click 'Load Charts' to view data");
        chart.setNoDataTextColor(Color.GRAY);
    }

    private void setupListeners() {
        realtimeTab.setOnClickListener(v -> switchToRealtimeView());
        analysisTab.setOnClickListener(v -> switchToAnalysisView());

        connectButton.setOnClickListener(v -> connectMqtt());
        disconnectButton.setOnClickListener(v -> disconnectMqtt());

        timeRangeGroup.setOnCheckedChangeListener((group, checkedId) -> {
            if (checkedId == R.id.radio24h) {
                selectedTimeRange = "24h";
            } else if (checkedId == R.id.radio30d) {
                selectedTimeRange = "30d";
            } else if (checkedId == R.id.radio12m) {
                selectedTimeRange = "12m";
            }
        });

        loadChartsButton.setOnClickListener(v -> loadChartData());
    }

    private void switchToRealtimeView() {
        isRealtimeView = true;
        realtimeView.setVisibility(View.VISIBLE);
        analysisView.setVisibility(View.GONE);

        realtimeTab.setEnabled(false);
        analysisTab.setEnabled(true);
    }

    private void switchToAnalysisView() {
        isRealtimeView = false;
        realtimeView.setVisibility(View.GONE);
        analysisView.setVisibility(View.VISIBLE);

        realtimeTab.setEnabled(true);
        analysisTab.setEnabled(false);
    }

    private void updateConnectionState(boolean connected) {
        isConnected = connected;
        loadChartsButton.setEnabled(connected);

        if (!connected) {
            chartStatusText.setText("Connect to MQTT to load charts");
        } else {
            chartStatusText.setText("");
        }
    }

    // ==================== DECRYPTION ====================

    private int decrypt(String base64Payload) throws Exception {
        byte[] raw = Base64.decode(base64Payload, Base64.DEFAULT);

        byte[] nonce = new byte[16];
        byte[] tag = new byte[16];
        byte[] ciphertext = new byte[raw.length - 32];

        System.arraycopy(raw, 0, nonce, 0, 16);
        System.arraycopy(raw, 16, ciphertext, 0, ciphertext.length);
        System.arraycopy(raw, raw.length - 16, tag, 0, 16);

        byte[] ciphertextWithTag = new byte[ciphertext.length + tag.length];
        System.arraycopy(ciphertext, 0, ciphertextWithTag, 0, ciphertext.length);
        System.arraycopy(tag, 0, ciphertextWithTag, ciphertext.length, tag.length);

        byte[] keyBytes = hexStringToByteArray(AES_KEY_HEX);
        SecretKeySpec keySpec = new SecretKeySpec(keyBytes, "AES");

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding", "BC");
        GCMParameterSpec gcmSpec = new GCMParameterSpec(GCM_TAG_LENGTH, nonce);
        cipher.init(Cipher.DECRYPT_MODE, keySpec, gcmSpec);

        byte[] plaintext = cipher.doFinal(ciphertextWithTag);
        String valueStr = new String(plaintext, StandardCharsets.UTF_8);
        return Integer.parseInt(valueStr);
    }

    private byte[] hexStringToByteArray(String hex) {
        int len = hex.length();
        byte[] data = new byte[len / 2];
        for (int i = 0; i < len; i += 2) {
            data[i / 2] = (byte) ((Character.digit(hex.charAt(i), 16) << 4)
                    + Character.digit(hex.charAt(i + 1), 16));
        }
        return data;
    }

    // ==================== NOTIFICATIONS ====================

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            CharSequence name = "Emergency Alerts";
            String description = "Critical security alerts";
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
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

    // ==================== REALTIME MQTT ====================

    private void connectMqtt() {
        runOnUiThread(() -> {
            statusText.setText("Connecting...");
            statusText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
            connectButton.setEnabled(false);
        });

        new Thread(() -> {
            try {
                realtimeMqttClient = MqttClient.builder()
                        .useMqttVersion3()
                        .identifier("AndroidRealtime_" + UUID.randomUUID().toString().substring(0, 8))
                        .serverHost(brokerHost)
                        .serverPort(brokerPort)
                        .sslWithDefaultConfig()
                        .buildAsync();

                Log.d(TAG, "Connecting to MQTT broker with TLS...");

                realtimeMqttClient.connectWith()
                        .send()
                        .whenComplete((connAck, throwable) -> {
                            if (throwable != null) {
                                Log.e(TAG, "Connection failed", throwable);
                                runOnUiThread(() -> {
                                    statusText.setText("Connection failed ✗");
                                    statusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                                    connectButton.setEnabled(true);
                                    disconnectButton.setEnabled(false);
                                    updateConnectionState(false);
                                    Toast.makeText(this, "Failed: " + throwable.getMessage(),
                                            Toast.LENGTH_LONG).show();
                                });
                            } else {
                                Log.d(TAG, "Connected successfully!");
                                runOnUiThread(() -> {
                                    statusText.setText("Connected ✓ (TLS + AES-256)");
                                    statusText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
                                    connectButton.setEnabled(false);
                                    disconnectButton.setEnabled(true);
                                    updateConnectionState(true);
                                    Toast.makeText(this, "Connected securely!",
                                            Toast.LENGTH_SHORT).show();
                                });

                                subscribeToRealtimeTopics();
                            }
                        });

            } catch (Exception e) {
                Log.e(TAG, "Error creating MQTT client", e);
                runOnUiThread(() -> {
                    statusText.setText("Error: " + e.getMessage());
                    statusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                    connectButton.setEnabled(true);
                    disconnectButton.setEnabled(false);
                    updateConnectionState(false);
                });
            }
        }).start();
    }

    private void disconnectMqtt() {
        if (realtimeMqttClient != null && realtimeMqttClient.getState().isConnected()) {
            realtimeMqttClient.disconnect().whenComplete((v, throwable) -> {
                runOnUiThread(() -> {
                    statusText.setText("Disconnected");
                    statusText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    connectButton.setEnabled(true);
                    disconnectButton.setEnabled(false);
                    updateConnectionState(false);

                    flameText.setText("Waiting...");
                    flameText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    gasText.setText("Waiting...");
                    gasText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    waterText.setText("Waiting...");
                    waterText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));
                    lightText.setText("Waiting...");
                    lightText.setTextColor(getResources().getColor(R.color.status_info, getTheme()));

                    lastFlameEmergency = false;
                    lastGasEmergency = false;
                    lastWaterEmergency = false;

                    Toast.makeText(this, "Disconnected", Toast.LENGTH_SHORT).show();
                });
            });
        }
    }

    private void subscribeToRealtimeTopics() {
        realtimeMqttClient.subscribeWith()
                .topicFilter(realtimeTopic + "#")
                .callback(this::handleRealtimeMessage)
                .send()
                .whenComplete((subAck, throwable) -> {
                    if (throwable != null) {
                        Log.e(TAG, "Subscribe failed", throwable);
                    } else {
                        Log.d(TAG, "Subscribed to realtime data");
                    }
                });
    }

    private void handleRealtimeMessage(Mqtt3Publish publish) {
        String topic = publish.getTopic().toString();
        String encryptedPayload = new String(publish.getPayloadAsBytes(), StandardCharsets.UTF_8);

        runOnUiThread(() -> {
            try {
                int value = decrypt(encryptedPayload);
                Log.d(TAG, "Decrypted " + topic + ": " + value);

                if (topic.endsWith("flame")) {
                    updateFlameStatus(value);
                } else if (topic.endsWith("gas")) {
                    updateGasStatus(value);
                } else if (topic.endsWith("water")) {
                    updateWaterStatus(value);
                } else if (topic.endsWith("light")) {
                    updateLightStatus(value);
                }
            } catch (Exception e) {
                Log.e(TAG, "Decryption failed: " + e.getMessage());
            }
        });
    }

    // ==================== SENSOR STATUS UPDATES ====================

    private void updateFlameStatus(int value) {
        if (value >= 800) {
            flameText.setText("Good (" + value + ")");
            flameText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
            lastFlameEmergency = false;
        } else if (value >= 400) {
            flameText.setText("Heat (" + value + ")");
            flameText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
            lastFlameEmergency = false;
        } else {
            flameText.setText("FIRE! (" + value + ")");
            flameText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));

            if (!lastFlameEmergency) {
                sendEmergencyNotification("🔥 FIRE DETECTED!", "Check immediately!", 1);
                lastFlameEmergency = true;
            }
        }
    }

    private void updateGasStatus(int value) {
        if (value <= 150) {
            gasText.setText("Good (" + value + ")");
            gasText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
            lastGasEmergency = false;
        } else if (value <= 500) {
            gasText.setText("Minor Leak (" + value + ")");
            gasText.setTextColor(getResources().getColor(R.color.status_warning, getTheme()));
            lastGasEmergency = false;
        } else {
            gasText.setText("GAS LEAK! (" + value + ")");
            gasText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));

            if (!lastGasEmergency) {
                sendEmergencyNotification("💨 GAS LEAK!", "Evacuate now!", 2);
                lastGasEmergency = true;
            }
        }
    }

    private void updateWaterStatus(int value) {
        if (value == 0) {
            waterText.setText("Good (Dry)");
            waterText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
            lastWaterEmergency = false;
        } else {
            waterText.setText("WATER! (" + value + ")");
            waterText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));

            if (!lastWaterEmergency) {
                sendEmergencyNotification("💧 WATER DETECTED!", "Check for flooding!", 3);
                lastWaterEmergency = true;
            }
        }
    }

    private void updateLightStatus(int value) {
        if (value < 512) {
            lightText.setText("Dark (" + value + ")");
            lightText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
        } else {
            lightText.setText("Bright (" + value + ")");
            lightText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
        }
    }

    // ==================== CHART DATA LOADING ====================

    private void loadChartData() {
        if (!isConnected) {
            Toast.makeText(this, "Please connect to MQTT first", Toast.LENGTH_SHORT).show();
            return;
        }

        chartLoadingProgress.setVisibility(View.VISIBLE);
        loadChartsButton.setEnabled(false);
        chartStatusText.setText("Loading...");
        chartsLoaded = 0;

        // Setup timeout
        chartTimeoutRunnable = () -> {
            if (chartLoadingProgress.getVisibility() == View.VISIBLE) {
                chartLoadingProgress.setVisibility(View.GONE);
                loadChartsButton.setEnabled(true);
                chartStatusText.setText("Timeout: Charts server not responding");
                chartStatusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                Toast.makeText(this, "Chart loading timeout. Is Graphs_Tester.py running?", Toast.LENGTH_LONG).show();

                if (chartMqttClient != null && chartMqttClient.getState().isConnected()) {
                    chartMqttClient.disconnect();
                }
            }
        };
        chartTimeoutHandler.postDelayed(chartTimeoutRunnable, CHART_LOAD_TIMEOUT_MS);

        new Thread(() -> {
            try {
                chartMqttClient = MqttClient.builder()
                        .useMqttVersion3()
                        .identifier("AndroidChart_" + UUID.randomUUID().toString().substring(0, 8))
                        .serverHost(brokerHost)
                        .serverPort(brokerPort)
                        .sslWithDefaultConfig()
                        .buildAsync();

                chartMqttClient.connectWith()
                        .send()
                        .whenComplete((connAck, throwable) -> {
                            if (throwable != null) {
                                chartTimeoutHandler.removeCallbacks(chartTimeoutRunnable);
                                runOnUiThread(() -> {
                                    chartLoadingProgress.setVisibility(View.GONE);
                                    loadChartsButton.setEnabled(true);
                                    chartStatusText.setText("Connection failed");
                                    chartStatusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                                    Toast.makeText(this, "Failed to connect for charts", Toast.LENGTH_SHORT).show();
                                });
                            } else {
                                subscribeAndRequestCharts();
                            }
                        });

            } catch (Exception e) {
                chartTimeoutHandler.removeCallbacks(chartTimeoutRunnable);
                runOnUiThread(() -> {
                    chartLoadingProgress.setVisibility(View.GONE);
                    loadChartsButton.setEnabled(true);
                    chartStatusText.setText("Error");
                    chartStatusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
                });
            }
        }).start();
    }

    private void subscribeAndRequestCharts() {
        chartMqttClient.subscribeWith()
                .topicFilter(chartResponseTopic)
                .callback(this::handleChartResponse)
                .send()
                .whenComplete((subAck, throwable) -> {
                    if (throwable == null) {
                        requestChartForSensor("flame");
                        requestChartForSensor("gas");
                        requestChartForSensor("water");
                    }
                });
    }

    private void requestChartForSensor(String sensor) {
        try {
            JSONObject request = new JSONObject();
            request.put("sensor", sensor);
            request.put("range", selectedTimeRange);

            chartMqttClient.publishWith()
                    .topic(chartRequestTopic)
                    .payload(request.toString().getBytes(StandardCharsets.UTF_8))
                    .send();

            Log.d(TAG, "Requested chart for " + sensor + " (" + selectedTimeRange + ")");
        } catch (Exception e) {
            Log.e(TAG, "Failed to request chart", e);
        }
    }

    private void handleChartResponse(Mqtt3Publish publish) {
        String jsonData = new String(publish.getPayloadAsBytes(), StandardCharsets.UTF_8);

        runOnUiThread(() -> {
            try {
                JSONObject data = new JSONObject(jsonData);

                if (data.has("error")) {
                    Log.e(TAG, "Chart error: " + data.getString("error"));
                    return;
                }

                String sensor = data.getString("sensor");
                JSONArray points = data.getJSONArray("points");

                LineChart chart = null;
                int color = Color.GRAY;

                if (sensor.equals("flame")) {
                    chart = flameChart;
                    color = Color.rgb(244, 67, 54);
                } else if (sensor.equals("gas")) {
                    chart = gasChart;
                    color = Color.rgb(255, 193, 7);
                } else if (sensor.equals("water")) {
                    chart = waterChart;
                    color = Color.rgb(33, 150, 243);
                }

                if (chart != null) {
                    updateChartWithData(chart, points, sensor, color);
                }

                chartsLoaded++;
                if (chartsLoaded >= 3) {
                    chartTimeoutHandler.removeCallbacks(chartTimeoutRunnable);
                    chartLoadingProgress.setVisibility(View.GONE);
                    loadChartsButton.setEnabled(true);
                    chartStatusText.setText("Charts loaded ✓");
                    chartStatusText.setTextColor(getResources().getColor(R.color.status_good, getTheme()));
                    chartsLoaded = 0;

                    if (chartMqttClient != null && chartMqttClient.getState().isConnected()) {
                        chartMqttClient.disconnect();
                    }
                }

            } catch (Exception e) {
                Log.e(TAG, "Error parsing chart data", e);
                chartTimeoutHandler.removeCallbacks(chartTimeoutRunnable);
                chartLoadingProgress.setVisibility(View.GONE);
                loadChartsButton.setEnabled(true);
                chartStatusText.setText("Error loading charts");
                chartStatusText.setTextColor(getResources().getColor(R.color.status_danger, getTheme()));
            }
        });
    }

    private void updateChartWithData(LineChart chart, JSONArray points, String label, int color) throws Exception {
        List<Entry> entries = new ArrayList<>();

        for (int i = 0; i < points.length(); i++) {
            JSONObject point = points.getJSONObject(i);
            float avg = (float) point.getDouble("avg");
            entries.add(new Entry(i, avg));
        }

        if (entries.isEmpty()) {
            chart.clear();
            chart.setNoDataText("No data available for this period");
            chart.invalidate();
            return;
        }

        LineDataSet dataSet = new LineDataSet(entries, label);
        dataSet.setColor(color);
        dataSet.setCircleColor(color);
        dataSet.setLineWidth(2f);
        dataSet.setCircleRadius(3f);
        dataSet.setDrawCircleHole(false);
        dataSet.setValueTextSize(0f);
        dataSet.setDrawFilled(false);
        dataSet.setMode(LineDataSet.Mode.CUBIC_BEZIER);

        LineData lineData = new LineData(dataSet);
        chart.setData(lineData);
        chart.invalidate();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (chartTimeoutHandler != null && chartTimeoutRunnable != null) {
            chartTimeoutHandler.removeCallbacks(chartTimeoutRunnable);
        }
        if (realtimeMqttClient != null && realtimeMqttClient.getState().isConnected()) {
            realtimeMqttClient.disconnect();
        }
        if (chartMqttClient != null && chartMqttClient.getState().isConnected()) {
            chartMqttClient.disconnect();
        }
    }
}