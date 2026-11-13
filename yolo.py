import cv2
import time
import json
import os
from picamera2 import Picamera2
from ultralytics import YOLO
from adafruit_servokit import ServoKit

# Load Presets from File
PRESETS_FILE = "presets.json"

def load_presets():
    if os.path.exists(PRESETS_FILE):
        with open(PRESETS_FILE, "r") as f:
            return json.load(f)
    return {"left": {"horizontal": 45, "vertical": 90},
            "middle": {"horizontal": 90, "vertical": 90},
            "right": {"horizontal": 135, "vertical": 90}}  # Default presets

presets = load_presets()

# Initialize Servo Controller
kit = ServoKit(channels=16)

# Set servos to the last saved position
angle_horizontal = presets["middle"]["horizontal"]
angle_vertical = presets["middle"]["vertical"]
current_position = "middle"  # Start in middle
last_move_time = 0  
no_person_frames = 0  
FRAME_THRESHOLD = 3  
has_moved_after_lost = False  

kit.servo[0].angle = angle_horizontal
kit.servo[1].angle = angle_vertical

# Function to move servo using presets
def set_position(position):
    global current_position, last_move_time, has_moved_after_lost
    if position in presets:
        kit.servo[0].angle = presets[position]["horizontal"]
        kit.servo[1].angle = presets[position]["vertical"]
        current_position = position
        last_move_time = time.time()
        has_moved_after_lost = True
        print(f"Moved to {position}")

# Camera setup
picam2 = Picamera2()
picam2.preview_configuration.main.size = (640, 640)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# Load YOLO model
model = YOLO("yolo11n_ncnn_model")
objects_to_detect = [0]  
last_known_x = None  

while True:
    frame = picam2.capture_array()
    results = model(frame, imgsz=320, classes=0)
    detected_objects = results[0].boxes.cls.tolist()

    object_found = False
    for obj_id in objects_to_detect:
        if obj_id in detected_objects:
            object_found = True
            xywhn = results[0].boxes.xywhn  
            last_known_x = xywhn[0][0].item()  
            print(f"Person detected at X: {last_known_x}")
            no_person_frames = 0  
            has_moved_after_lost = False  

    if not object_found:
        no_person_frames += 1  
    else:
        no_person_frames = 0  

    if (
        no_person_frames >= FRAME_THRESHOLD and  
        last_known_x is not None and
        not has_moved_after_lost and  
        (time.time() - last_move_time) >= 2  
    ):
        if last_known_x < 0.5:  
            if current_position == "right":
                set_position("middle")  
            elif current_position != "left":
                set_position("left")

        elif last_known_x >= 0.5:  
            if current_position == "left":
                set_position("middle")  
            elif current_position != "right":
                set_position("right")

    # Annotate frame
    annotated_frame = results[0].plot()
    inference_time = results[0].speed['inference']
    fps = 1000 / inference_time  
    text = f'FPS: {fps:.1f}'
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 1, 2)[0]
    text_x = annotated_frame.shape[1] - text_size[0] - 10
    text_y = text_size[1] + 10
    cv2.putText(annotated_frame, text, (text_x, text_y), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.imshow("Camera", annotated_frame)

    if cv2.waitKey(1) == ord("q"):
        break

cv2.destroyAllWindows()