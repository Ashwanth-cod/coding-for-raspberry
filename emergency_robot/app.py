import serial
import os
import cv2
import numpy as np
import threading
import time
from flask import Flask, render_template, request, jsonify, Response

# --- SYSTEM DETECTION ---
try:
    import RPi.GPIO as GPIO
    IS_PI = True
except ImportError:
    IS_PI = False

app = Flask(__name__)

# --- GLOBAL DATA ---
sensor_data = {
    "fire_visual": False,
    "fire_thermal": False,
    "gas_level": 0,
    "vibration": False,
    "distance": 100
}

robot_state = {
    "mode": "AUTO_ROAM",  # Starts in Roam
    "medkit_deployed": False,
    "status": "Initializing..."
}

# --- HARDWARE CONFIG ---
LIGHT_PIN = 23
SERVO_PIN = 18

if IS_PI:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LIGHT_PIN, GPIO.OUT)
    GPIO.setup(SERVO_PIN, GPIO.OUT)
    pwm = GPIO.PWM(SERVO_PIN, 50)
    pwm.start(0)

# --- SMART SERIAL RECONNECT ---
ser = None
def connect_arduino():
    global ser
    port = '/dev/ttyACM0' if IS_PI else 'COM3'
    try:
        ser = serial.Serial(port, 9600, timeout=0.1)
        print(f"Connected to Arduino on {port}")
    except:
        ser = None
        print("Waiting for Arduino...")

connect_arduino()

# --- PI BRAIN: VISION ANALYSIS ---
def analyze_fire(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([18, 50, 50]), np.array([35, 255, 255]))
    return cv2.countNonZero(mask) > 1200

# --- PI BRAIN: THE MASTER MISSION LOOP ---
def mission_commander():
    """The Pi logic controller for the 10s/3s cycle"""
    global robot_state
    while True:
        if robot_state["mode"] == "AUTO_ROAM":
            # 10 SECOND ROAM
            robot_state["status"] = "Roaming (10s)"
            if ser: ser.write(b'F')
            time.sleep(10)

            # 3 SECOND SCAN
            if robot_state["mode"] == "AUTO_ROAM":
                robot_state["status"] = "Scanning (3s)"
                if ser: ser.write(b'S')
                time.sleep(1) # Settle time
                
                # Logic: Is there a fire?
                if sensor_data["fire_visual"] and sensor_data["fire_thermal"]:
                    emergency_event("FIRE CONFIRMED")
                
                # Logic: Is there a gas leak?
                if sensor_data["gas_level"] > 60:
                    emergency_event("GAS LEAK")
                    
                time.sleep(2)
        time.sleep(0.1)

def emergency_event(reason):
    global robot_state
    robot_state["mode"] = "EMERGENCY"
    robot_state["status"] = f"CRITICAL: {reason}"
    if ser: ser.write(b'S')
    if IS_PI:
        os.system(f'espeak "Emergency. {reason} detected." &')
        GPIO.output(LIGHT_PIN, GPIO.HIGH)

# --- BACKGROUND DATA CAPTURE ---
def arduino_listener():
    global sensor_data
    while True:
        if ser:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8').strip()
                    parts = line.split('|')
                    for p in parts:
                        k, v = p.split(':')
                        if k == 'D': sensor_data["distance"] = int(v)
                        if k == 'G': sensor_data["gas_level"] = int(v)
                        if k == 'F': sensor_data["fire_thermal"] = (v == '1')
                        if k == 'V': sensor_data["vibration"] = (v == '1')
            except:
                connect_arduino() # Try to reconnect if error
        else:
            connect_arduino()
        time.sleep(0.05)

threading.Thread(target=arduino_listener, daemon=True).start()
threading.Thread(target=mission_commander, daemon=True).start()

# --- CAMERA FEED ---
def gen_frames():
    # In Lite, we use a lower resolution to save CPU
    cap = cv2.VideoCapture(0)
    cap.set(3, 320); cap.set(4, 240) 
    while True:
        success, frame = cap.read()
        if not success: break
        sensor_data["fire_visual"] = analyze_fire(frame)
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/video')
def video_feed(): return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/sensor_data')
def get_sensors(): return jsonify({**sensor_data, **robot_state})

@app.route('/action', methods=['POST'])
def action():
    act = request.json.get('action')
    if act == "MEDKIT":
        if IS_PI:
            pwm.ChangeDutyCycle(7.5); time.sleep(1.5); pwm.ChangeDutyCycle(0)
            os.system('espeak "Med kit open." &')
        robot_state["medkit_deployed"] = True
        return jsonify({"status": "ok"})
    return jsonify({"status": "err"})

@app.route('/move', methods=['POST'])
def move():
    robot_state["mode"] = "MANUAL"
    cmd = request.json.get('move')
    move_map = {"FORWARD": b'F', "BACK": b'B', "LEFT": b'L', "RIGHT": b'R', "STOP": b'S'}
    if ser: ser.write(move_map.get(cmd, b'S'))
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)