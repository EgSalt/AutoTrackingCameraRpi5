import atexit
import subprocess
from flask import Flask, Response, render_template, send_from_directory, jsonify, request
from flask_cors import CORS
from picamera2 import Picamera2
import cv2
from adafruit_servokit import ServoKit
import os
import sys
import json
kit = ServoKit(channels=16)
angle_horizontal = 100
angle_vertical = 92
kit.servo[0].angle = angle_horizontal
kit.servo[1].angle = angle_vertical

app = Flask(__name__)
CORS(app)

FLUTTER_WEB_APP = 'templates'
PRESETS_FILE = "presets.json"

# Preset positions
presets = {
    "left": {"horizontal": 45, "vertical": 90},
    "middle": {"horizontal": 90, "vertical": 90},
    "right": {"horizontal": 135, "vertical": 90},
}

# Save presets to a file
def save_presets_to_file():
    with open(PRESETS_FILE, "w") as f:
        json.dump(presets, f)
    print("Presets saved successfully.")

YOLO_PROCESS_FILE = "yolo_pid.txt"  # File to store the process ID

@app.route('/final_save_and_exit', methods=['POST'])
def final_save_and_exit():
    global picam2
    save_presets_to_file()
    print("Final positions saved. Releasing camera and starting YOLO...")

    if picam2:
        picam2.stop()
        picam2.close()
        print("Camera released.")

    # Start YOLO script & save its process ID
    process = subprocess.Popen(["python3", "yolo.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(YOLO_PROCESS_FILE, "w") as f:
        f.write(str(process.pid))  # Store process ID

    # Shut down Flask properly
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
    
    return jsonify({"message": "Server shutting down, YOLO script started!"})

@app.route('/stop_yolo', methods=['POST'])
def stop_yolo():
    if os.path.exists(YOLO_PROCESS_FILE):
        with open(YOLO_PROCESS_FILE, "r") as f:
            pid = int(f.read().strip())

        try:
            os.kill(pid, 9)  # Force kill the process
            os.remove(YOLO_PROCESS_FILE)  # Delete the PID file
            return jsonify({"message": "YOLO script stopped!"})
        except ProcessLookupError:
            return jsonify({"error": "Process not found!"}), 400
    else:
        return jsonify({"error": "YOLO is not running!"}), 400

# ? Set servo angles to a saved position (Left, Middle, Right)
@app.route('/set_position', methods=['POST'])
def set_position():
    global angle_horizontal, angle_vertical
    data = request.json
    position = data.get("position")

    if position in presets:
        angle_horizontal = presets[position]["horizontal"]
        angle_vertical = presets[position]["vertical"]

        # Move servos
        kit.servo[0].angle = angle_horizontal
        kit.servo[1].angle = angle_vertical

        return jsonify({"message": f"Moved to {position}", "angles": presets[position]})
    else:
        return jsonify({"error": "Invalid position"}), 400

# ? Save a new position preset
@app.route('/save_position', methods=['POST'])
def save_position():
    data = request.json
    position = data.get("position")
    horizontal = data.get("horizontal")
    vertical = data.get("vertical")

    if position and horizontal is not None and vertical is not None:
        presets[position] = {"horizontal": angle_horizontal, "vertical": angle_vertical}
        return jsonify({"message": f"Saved {position} position", "angles": presets[position]})
    else:
        return jsonify({"error": "Invalid data"}), 400

@app.route('/horizontal_servo_angle', methods=['GET'])
def get_servo_angle_horizontal():
    return jsonify({"angle": angle_horizontal})

@app.route('/vertical_servo_angle', methods=['GET'])
def get_servo_angle_vertical():
    return jsonify({"angle": angle_vertical})

# ? Update horizontal servo angle
@app.route('/update_horizontal_angle', methods=['POST'])
def update_horizontal_angle():
    global angle_horizontal
    data = request.json
    angle_horizontal += data.get('change', 0)
    angle_horizontal = max(0, min(180, angle_horizontal))  # Clamp between 0-180
    
    # Move the servo (Assuming horizontal servo is on channel 0)
    kit.servo[0].angle = angle_horizontal

    return jsonify({"angle": angle_horizontal})

# ? Update vertical servo angle
@app.route('/update_vertical_angle', methods=['POST'])
def update_vertical_angle():
    global angle_vertical
    data = request.json
    angle_vertical += data.get('change', 0)
    angle_vertical = max(0, min(180, angle_vertical))

    # Move the servo (Assuming vertical servo is on channel 1)
    kit.servo[1].angle = angle_vertical

    return jsonify({"angle": angle_vertical})

@app.route('/')
def render_page():
    return render_template('index.html')

@app.route('/web/')
def render_page_web():
    return render_template('index.html')

@app.route('/web/<path:name>')
def return_flutter_doc(name):
    datalist = str(name).split('/')
    DIR_NAME = FLUTTER_WEB_APP

    if len(datalist) > 1:
        for i in range(0, len(datalist) - 1):
            DIR_NAME += '/' + datalist[i]

    return send_from_directory(DIR_NAME, datalist[-1])

# Initialize Picamera2
picam2 = Picamera2()
picam2.preview_configuration.main.size = (640, 480)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# Cleanup function
def release_camera():
    print("Releasing camera...")
    picam2.stop()
atexit.register(release_camera)

# Route to serve a single JPEG image
@app.route('/current_frame')
def current_frame():
    frame = picam2.capture_array()
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    _, buffer = cv2.imencode('.jpg', frame)
    
    return Response(buffer.tobytes(), mimetype='image/jpeg')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)