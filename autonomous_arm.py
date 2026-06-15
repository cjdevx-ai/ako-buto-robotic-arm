import cv2
import os
import argparse
import time
import numpy as np
import csv
import serial
import serial.tools.list_ports
from inference_sdk import InferenceHTTPClient
from dotenv import load_dotenv
import supervision as sv

# Load environment variables from .env file
load_dotenv()

# Constants
START_POS = [180, 90, 150, 40, 90, 0]
DROP_ANGLES = {
    "PEANUT": [147, 163, 80, 25, 90, 0],
    "PUMPKIN": [116, 142, 58, 19, 90, 0],
    "SUNFLOWER": [65, 130, 30, 10, 90, 0]
}

def load_mapping(csv_path):
    mapping = {}
    if not os.path.exists(csv_path):
        print(f"Error: Mapping file {csv_path} not found.")
        return mapping
    
    try:
        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # Strip whitespace from headers
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            
            for row in reader:
                try:
                    x = int(row['x'].strip())
                    y = int(row['y'].strip())
                    angles = [
                        int(row['s0'].strip()), int(row['s1'].strip()), int(row['s2'].strip()),
                        int(row['s3'].strip()), int(row['s4'].strip()), int(row['s5'].strip())
                    ]
                    mapping[(x, y)] = angles
                except (ValueError, KeyError, TypeError) as e:
                    print(f" - Skipping invalid row: {row} (Error: {e})")
                    continue
    except Exception as e:
        print(f"Error reading mapping file: {e}")
        
    print(f"Successfully loaded {len(mapping)} coordinate mappings.")
    return mapping

def send_angles(ser, angles):
    if ser and ser.is_open:
        cmd = ",".join(f"{i}:{v}" for i, v in enumerate(angles))
        ser.write((cmd + "\n").encode())
        print(f" - Sent angles: {cmd}")

def main():
    parser = argparse.ArgumentParser(description="Autonomous Arm - Object Detection every 5 seconds")
    parser.add_argument('--index', type=int, default=1, help='OpenCV camera index (default: 1)')
    parser.add_argument('--model_id', type=str, help='Roboflow model ID (overrides .env)')
    parser.add_argument('--api_key', type=str, help='Roboflow API Key (overrides .env)')
    parser.add_argument('--confidence', type=float, default=0.5, help='Confidence threshold (default: 0.5)')
    parser.add_argument('--roi_size', type=float, default=0.6, help='Size of ROI box as a fraction of frame (0.0 to 1.0)')
    parser.add_argument('--interval', type=float, default=5.0, help='Interval between detections in seconds (default: 5.0)')
    parser.add_argument('--port', type=str, help='Serial port for ESP32 (e.g., COM9)')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate (default: 115200)')

    args = parser.parse_args()

    # Load coordinate mapping
    mapping = load_mapping("map.csv")
    if mapping:
        sample_keys = list(mapping.keys())[:5]
        print(f"Sample mapping keys: {sample_keys}")
    
    # Serial Setup
    ser = None
    port = args.port
    if not port:
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        if available_ports:
            port = available_ports[0]
            print(f"Auto-detected serial port: {port}")
    
    if port:
        try:
            ser = serial.Serial(port, args.baud, timeout=1)
            time.sleep(2) # Wait for ESP32 to reset
            print(f"Connected to ESP32 on {port}")
            # Move to starting position
            send_angles(ser, START_POS)
        except Exception as e:
            print(f"Error connecting to serial port {port}: {e}")
    else:
        print("Warning: No serial port found. Arm movements will be skipped.")

    # Configuration
    api_url = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")
    api_key = args.api_key or os.getenv("ROBOFLOW_API_KEY")
    model_id = args.model_id or os.getenv("ROBOFLOW_MODEL_ID", "ako_buto/4")

    if not api_key:
        print("Error: Roboflow API Key not found. Please set it in .env or via --api_key.")
        return

    # Initialize the client
    client = InferenceHTTPClient(
        api_url=api_url,
        api_key=api_key
    )

    # Initialize annotators for visualization
    box_annotator = sv.BoxAnnotator(thickness=1)
    label_annotator = sv.LabelAnnotator(text_scale=0.4, text_thickness=1, text_padding=2)

    # Open the camera
    cap = cv2.VideoCapture(args.index)

    if not cap.isOpened():
        print(f"Error: Could not open camera with index {args.index}")
        return

    print(f"Starting autonomous arm detection from camera {args.index}...")
    print(f"Model ID: {model_id}")
    print(f"Detection interval: {args.interval} seconds.")
    print("Press 'q' to quit.")

    last_detection_time = 0
    latest_detections = sv.Detections.empty()
    latest_labels = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_time = time.time()
        height, width, _ = frame.shape
        
        # Define ROI (Region of Interest) Box (exact logic from roboflow_live.py)
        roi_w_full, roi_h = int(width * args.roi_size), int(height * args.roi_size)
        x1, y1 = (width - roi_w_full) // 2, (height - roi_h) // 2
        
        # Reduce ROI size 1/4 from the right
        roi_w = int(roi_w_full * 0.75)
        x2, y2 = x1 + roi_w, y1 + roi_h
        
        # Draw ROI Box on the display frame
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(frame, "ROI", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        # Periodic Detection
        if current_time - last_detection_time >= args.interval:
            last_detection_time = current_time
            print(f"\n[{time.strftime('%H:%M:%S')}] Capturing image and detecting...")
            
            try:
                result = client.infer(frame, model_id=model_id)
                detections = sv.Detections.from_inference(result)
                
                # Filter by confidence
                detections = detections[detections.confidence >= args.confidence]

                if len(detections) > 0:
                    centers = []
                    valid_indices = []
                    first_valid_obj = None

                    for i, bbox in enumerate(detections.xyxy):
                        cx, cy = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
                        if x1 <= cx <= x2 and y1 <= cy <= y2:
                            # Scale coordinates: x (0-15), y (0-11)
                            sx = (cx - x1) * 15 / roi_w
                            sy = (cy - y1) * 11 / roi_h
                            centers.append((sx, sy))
                            valid_indices.append(i)
                            
                            # Round and clamp to mapping bounds (x: 1-14, y: 1-10)
                            mx = int(np.clip(round(sx), 1, 14))
                            my = int(np.clip(round(sy), 1, 10))
                            
                            class_id = detections.class_id[i]
                            class_name = detections.data['class_name'][i].upper() if 'class_name' in detections.data else "UNKNOWN"
                            
                            if first_valid_obj is None:
                                first_valid_obj = {
                                    "mx": mx, "my": my, 
                                    "sx": sx, "sy": sy, 
                                    "class_name": class_name
                                }
                            
                            # Log the result
                            print(f" - Found {class_name} at Scaled Coords: X={sx:.2f}, Y={sy:.2f} (Map: {mx},{my})")
                    
                    # Update data for visualization
                    latest_detections = detections[valid_indices]
                    latest_labels = [f"{detections.data['class_name'][i].upper()}" for i in valid_indices]
                    
                    if first_valid_obj and ser:
                        mx, my = first_valid_obj["mx"], first_valid_obj["my"]
                        class_name = first_valid_obj["class_name"]
                        
                        if (mx, my) in mapping:
                            pick_angles = mapping[(mx, my)]
                            print(f"\n[ACTION] Starting pick-and-place for {class_name} at ({mx}, {my})...")
                            
                            # 1. Move to Pick Position
                            send_angles(ser, pick_angles)
                            time.sleep(1)
                            
                            # 2. Close Grip (s5=0)
                            send_angles(ser, pick_angles[:5] + [0])
                            time.sleep(1)
                            
                            # 3. Back to Starting Position
                            send_angles(ser, START_POS)
                            time.sleep(1)
                            
                            # 4. Move to Drop Position based on class
                            if class_name in DROP_ANGLES:
                                drop_angles = DROP_ANGLES[class_name]
                                send_angles(ser, drop_angles)
                                time.sleep(1)
                                
                                # 5. Open Grip (s5=30)
                                send_angles(ser, drop_angles[:5] + [30])
                                time.sleep(1)
                                
                                # 6. Back to Starting Position
                                send_angles(ser, START_POS)
                                time.sleep(1)
                            else:
                                print(f" - Warning: No drop angles defined for class {class_name}. Skipping drop.")
                            
                            # Enforce 4s delay before next detection
                            print(f"[SUCCESS] Cycle complete. Waiting 4s...")
                            # Set last_detection_time so the next interval triggers in 4 seconds
                            last_detection_time = time.time() + 4.0 - args.interval
                        else:
                            print(f" - Warning: No mapping found for ({mx}, {my}).")

                    if not centers:
                        print(" - No objects found within ROI.")
                        latest_detections = sv.Detections.empty()
                        latest_labels = []
                else:
                    print(" - No objects detected in frame.")
                    latest_detections = sv.Detections.empty()
                    latest_labels = []

            except Exception as e:
                print(f"Inference error: {e}")

        # Annotate the frame with the results from the last detection cycle
        if len(latest_detections) > 0:
            frame = box_annotator.annotate(scene=frame, detections=latest_detections)
            frame = label_annotator.annotate(scene=frame, detections=latest_detections, labels=latest_labels)

        # Visual feedback for the timer
        time_to_next = max(0, args.interval - (current_time - last_detection_time))
        cv2.putText(frame, f"Next detection in: {time_to_next:.1f}s", (20, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("Autonomous Arm Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
