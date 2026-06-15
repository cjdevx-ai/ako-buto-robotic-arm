import cv2
import os
import argparse
import numpy as np
from inference_sdk import InferenceHTTPClient
from dotenv import load_dotenv
import supervision as sv

# Load environment variables from .env file
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Roboflow Live Camera Detection with ROI")
    parser.add_argument('--index', type=int, default=1, help='OpenCV camera index (default: 0)')
    parser.add_argument('--model_id', type=str, help='Roboflow model ID (overrides .env)')
    parser.add_argument('--api_key', type=str, help='Roboflow API Key (overrides .env)')
    parser.add_argument('--confidence', type=float, default=0.5, help='Confidence threshold (default: 0.5)')
    parser.add_argument('--roi_size', type=float, default=0.6, help='Size of ROI box as a fraction of frame (0.0 to 1.0)')

    args = parser.parse_args()

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

    # Initialize annotators with reduced text size
    box_annotator = sv.BoxAnnotator(thickness=1)
    label_annotator = sv.LabelAnnotator(text_scale=0.4, text_thickness=1, text_padding=2)
    fps_monitor = sv.FPSMonitor()

    # Open the camera
    cap = cv2.VideoCapture(args.index)

    if not cap.isOpened():
        print(f"Error: Could not open camera with index {args.index}")
        return

    print(f"Starting live feed from camera {args.index}...")
    print("Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        height, width, _ = frame.shape
        
        # Define ROI (Region of Interest) Box
        roi_w_full, roi_h = int(width * args.roi_size), int(height * args.roi_size)
        x1, y1 = (width - roi_w_full) // 2, (height - roi_h) // 2
        
        # Reduce ROI size 1/4 from the right
        roi_w = int(roi_w_full * 0.75)
        x2, y2 = x1 + roi_w, y1 + roi_h
        
        # Draw ROI Box on the display frame
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(frame, "ROI", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.2, (255, 255, 0), 1)

        # Perform inference on the whole frame
        try:
            result = client.infer(frame, model_id=model_id)
            detections = sv.Detections.from_inference(result)
            
            # Filter by confidence
            detections = detections[detections.confidence >= args.confidence]

            if len(detections) > 0:
                # Filter detections that are inside the ROI center point
                # xyxy is [x1, y1, x2, y2]
                centers = []
                valid_indices = []
                
                for i, bbox in enumerate(detections.xyxy):
                    cx, cy = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
                    if x1 <= cx <= x2 and y1 <= cy <= y2:
                        # Scale coordinates: 
                        # x: 0 to 15
                        # y: 0 to 11
                        scaled_x = (cx - x1) * 15 / roi_w
                        scaled_y = (cy - y1) * 11 / roi_h
                        centers.append((scaled_x, scaled_y))
                        valid_indices.append(i)
                
                # Keep only detections inside ROI
                detections = detections[valid_indices]
                
                # Replace labels with scaled coordinates
                labels = [f"({x:.1f}, {y:.1f})" for x, y in centers]

                # Annotate the frame
                frame = box_annotator.annotate(scene=frame, detections=detections)
                frame = label_annotator.annotate(scene=frame, detections=detections, labels=labels)

        except Exception as e:
            print(f"Inference error: {e}")

        # Tick the FPS monitor
        fps_monitor.tick()
        fps = fps_monitor.fps
        
        # Display FPS with reduced size
        cv2.putText(frame, f"FPS: {fps:.1f}", (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        cv2.imshow("Roboflow Live Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
