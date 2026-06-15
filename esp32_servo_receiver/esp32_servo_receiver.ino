/*
 * ESP32 Servo Receiver for 6-DOF Robotic Arm
 * Listens for serial commands in the format:
 *   - "index:angle\n" (Single servo update)
 *   - "i1:v1,i2:v2,i3:v3...\n" (Bulk servo update)
 * 
 * Baud Rate: 115200
 */

#include <ESP32Servo.h>

const int NUM_SERVOS = 6;
const int SERVO_PINS[NUM_SERVOS] = {15, 18, 19, 21, 22, 23};
const int START_POS[NUM_SERVOS]  = {180, 90, 150, 40, 90, 0};

Servo servos[NUM_SERVOS];

void setup() {
  Serial.begin(115200);
  Serial.println("ESP32 Servo Receiver Starting...");

  // Allow allocation of all timers
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].setPeriodHertz(50); // Standard 50hz servo
    servos[i].attach(SERVO_PINS[i], 500, 2400); // Attach with min/max pulse width
    servos[i].write(START_POS[i]);
    Serial.printf("Servo %d attached to GPIO %d, set to %d deg\n", i, SERVO_PINS[i], START_POS[i]);
  }

  Serial.println("Ready for commands.");
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0) return;

    // Echo back for logging
    Serial.print("Recv: ");
    Serial.println(input);

    // Parse commands separated by commas
    int startIndex = 0;
    int commaIndex = input.indexOf(',');
    
    while (true) {
      String segment;
      if (commaIndex == -1) {
        segment = input.substring(startIndex);
      } else {
        segment = input.substring(startIndex, commaIndex);
      }
      
      processCommand(segment);
      
      if (commaIndex == -1) break;
      startIndex = commaIndex + 1;
      commaIndex = input.indexOf(',', startIndex);
    }
  }
}

void processCommand(String cmd) {
  int colonIndex = cmd.indexOf(':');
  if (colonIndex == -1) return;

  int idx = cmd.substring(0, colonIndex).toInt();
  int angle = cmd.substring(colonIndex + 1).toInt();

  if (idx >= 0 && idx < NUM_SERVOS) {
    // Clamp angle to safe range
    if (angle < 0) angle = 0;
    if (angle > 180) angle = 180;
    
    servos[idx].write(angle);
    Serial.printf("Servo %d -> %d deg\n", idx, angle);
  }
}
