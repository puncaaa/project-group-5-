void setup() {
  Serial.begin(9600);
  pinMode(2, INPUT);
}

void loop() {
  int flame = analogRead(A0);
  int gas   = analogRead(A1);
  int water = analogRead(A2);
  int light = digitalRead(2); // 0 или 1

  Serial.print("{");
  Serial.print("\"flame\":"); Serial.print(flame); Serial.print(",");
  Serial.print("\"gas\":");   Serial.print(gas);   Serial.print(",");
  Serial.print("\"water\":"); Serial.print(water); Serial.print(",");
  Serial.print("\"light\":"); Serial.print(light);
  Serial.println("}");

  delay(2000);
}