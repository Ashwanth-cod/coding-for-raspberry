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
    "distance": 100,
    "violence": False
}

robot_state = {
    "mode": "AUTO_ROAM",
    "medkit_deployed": False,
    "status": "Initializing..."
}

# --- HARDWARE CONFIG ---
LIGHT_PIN = 23
SERVO_PIN = 18
if IS_PI:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LIGHT_PIN, GPIO.OUT)
    GPIO.setup(SERVO_PIN, GPIO.OUT)
    pwm = GPIO.PWM(SERVO_PIN, 50)
    pwm.start(0)

# --- ARDUINO CONNECTION (Resilient) ---
ser = None
def connect_arduino():
    global ser
    # Port might be /dev/ttyUSB0 or /dev/ttyACM0
    ports = ['/dev/ttyACM0', '/dev/ttyUSB0'] if IS_PI else ['COM3']
    for port in ports:
        try:
            ser = serial.Serial(port, 9600, timeout=0.1)
            print(f"✅ Connected to Arduino on {port}")
            return
        except:
            continue
    ser = None

connect_arduino()

# --- VISION ANALYSIS ---
def analyze_fire(frame):
    try:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([18, 50, 50]), np.array([35, 255, 255]))
        return cv2.countNonZero(mask) > 1200
    except:
        return False

# --- MISSION LOOP ---
def mission_commander():
    while True:
        if robot_state["mode"] == "AUTO_ROAM":
            if ser: 
                ser.write(b'F')
                robot_state["status"] = "Roaming..."
            else:
                robot_state["status"] = "Roaming (No Arduino)"
            time.sleep(2)
        time.sleep(0.5)

# --- ARDUINO SENSOR LISTENER ---
def arduino_listener():
    global sensor_data
    while True:
        if ser:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    parts = line.split('|')
                    for p in parts:
                        if ':' in p:
                            k, v = p.split(':')
                            if k == 'D': sensor_data["distance"] = int(v)
                            if k == 'G': sensor_data["gas_level"] = int(v)
                            if k == 'F': sensor_data["fire_thermal"] = (v == '1')
                            if k == 'V': sensor_data["vibration"] = (v == '1')
                            if k == 'A': sensor_data["violence"] = (v == '1')
            except:
                connect_arduino()
        else:
            time.sleep(10) # Don't spam if Arduino is unplugged
            connect_arduino()
        time.sleep(0.1)

# Start background threads
threading.Thread(target=arduino_listener, daemon=True).start()
threading.Thread(target=mission_commander, daemon=True).start()

# --- CAMERA & RECORDING SYSTEM ---
RECORD_PATH = os.path.join(os.getcwd(), "recordings")
os.makedirs(RECORD_PATH, exist_ok=True)
recording_active = False
video_out = None

def gen_frames():
    global video_out, recording_active
    
    # On Pi Lite, we try standard index 0
    cap = cv2.VideoCapture(0)
    
    # Set resolution low for Pi performance
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    if not cap.isOpened():
        print("❌ CAMERA ERROR: Check ribbon cable or config.txt")
        while True:
            # Send black frame if camera fails so website doesn't hang
            blank = np.zeros((240, 320, 3), np.uint8)
            cv2.putText(blank, "CAMERA NOT FOUND", (20, 120), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            _, buffer = cv2.imencode('.jpg', blank)
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(1)

    while True:
        success, frame = cap.read()
        if not success:
            break

        # Detection logic
        sensor_data["fire_visual"] = analyze_fire(frame)

        # Recording Logic
        if recording_active:
            if video_out is None:
                ts = time.strftime("%Y%m%d-%H%M%S")
                filename = os.path.join(RECORD_PATH, f"rec_{ts}.avi")
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                video_out = cv2.VideoWriter(filename, fourcc, 15.0, (320, 240))
            video_out.write(frame)
        else:
            if video_out:
                video_out.release()
                video_out = None

        # Encode for streaming
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret: continue
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

    cap.release()

# --- FLASK ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/sensor_data')
def get_sensors():
    return jsonify({**sensor_data, **robot_state})

@app.route('/record', methods=['POST'])
def record():
    global recording_active
    data = request.get_json()
    recording_active = (data.get('status') == "start")
    return jsonify({"recording": recording_active})

@app.route('/move', methods=['POST'])
def move():
    robot_state["mode"] = "MANUAL"
    cmd = request.json.get('move')
    move_map = {"FORWARD": b'F', "BACK": b'B', "LEFT": b'L', "RIGHT": b'R', "STOP": b'S'}
    if ser: ser.write(move_map.get(cmd, b'S'))
    return jsonify({"status": "ok"})

@app.route('/action', methods=['POST'])
def action():
    act = request.json.get('action')
    state = request.json.get('state', False)
    if act == "LIGHTS" and IS_PI:
        GPIO.output(LIGHT_PIN, GPIO.HIGH if state else GPIO.LOW)
    elif act == "MEDKIT" and IS_PI:
        pwm.ChangeDutyCycle(7.5)
        time.sleep(1)
        pwm.ChangeDutyCycle(0)
        robot_state["medkit_deployed"] = True
    return jsonify({"status": "ok"})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    if IS_PI: os.system('sudo shutdown now')
    return jsonify({"status": "shutting down"})

if __name__ == '__main__':
    # threaded=True is REQUIRED for video streaming
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)