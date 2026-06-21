import cv2
import os
import argparse
import numpy as np
from ultralytics import YOLO
import supervision as sv

def main():
    parser = argparse.ArgumentParser(description="Optimized YOLO ONNX Live Camera Detection")
    parser.add_argument('--model', type=str, default='onnx_models/best.onnx', help='Path to ONNX model')
    parser.add_argument('--index', type=int, default=0, help='OpenCV camera index')
    parser.add_argument('--confidence', type=float, default=0.5, help='Confidence threshold')
    parser.add_argument('--roi_size', type=float, default=0.6, help='ROI size fraction')
    parser.add_argument('--imgsz', type=int, default=320, help='Inference image size')
    parser.add_argument('--half', action='store_true', help='Use half-precision (FP16) inference')

    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"Error: Model file '{args.model}' not found.")
        return

    # Load the ONNX model
    model = YOLO(args.model, task='detect')

    # Initialize annotators
    box_annotator = sv.BoxAnnotator(thickness=1)
    label_annotator = sv.LabelAnnotator(text_scale=0.4, text_thickness=1, text_padding=2)
    fps_monitor = sv.FPSMonitor()

    # Open the camera
    cap = cv2.VideoCapture(args.index)
    if not cap.isOpened():
        print(f"Error: Could not open camera {args.index}")
        return

    print(f"Starting OPTIMIZED live feed (ROI-only inference)...")
    print("Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        height, width, _ = frame.shape
        
        # Define ROI (matching your specific layout)
        roi_w_full, roi_h = int(width * args.roi_size), int(height * args.roi_size)
        x1, y1 = (width - roi_w_full) // 2, (height - roi_h) // 2
        roi_w = int(roi_w_full * 0.75) # 1/4 reduction from right
        x2, y2 = x1 + roi_w, y1 + roi_h
        
        # Crop the frame for inference
        roi_frame = frame[y1:y2, x1:x2]
        
        # Draw ROI Box on the display frame
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(frame, "ROI", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

        # Perform inference ONLY on the cropped ROI
        try:
            # Note: imgsz=args.imgsz will resize the CROP, making it very fast
            results = model(roi_frame, conf=args.confidence, imgsz=args.imgsz, half=args.half, verbose=False)[0]
            detections = sv.Detections.from_ultralytics(results)
            
            if len(detections) > 0:
                # 1. Scale coordinates for display labels (relative to ROI)
                centers = []
                for bbox in detections.xyxy:
                    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
                    scaled_x = cx * 15 / roi_w
                    scaled_y = cy * 11 / roi_h
                    centers.append((scaled_x, scaled_y))
                
                # 2. Offset bounding boxes back to the full frame coordinates
                # detections.xyxy is a numpy array: [x1, y1, x2, y2]
                detections.xyxy += np.array([x1, y1, x1, y1])
                
                # Prepare labels
                labels = [f"({x:.1f}, {y:.1f})" for x, y in centers]

                # Annotate the full frame
                frame = box_annotator.annotate(scene=frame, detections=detections)
                frame = label_annotator.annotate(scene=frame, detections=detections, labels=labels)

        except Exception as e:
            print(f"Inference error: {e}")

        # Tick the FPS monitor
        fps_monitor.tick()
        fps = fps_monitor.fps
        
        # Display FPS
        cv2.putText(frame, f"FPS: {fps:.1f} (Optimized)", (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        cv2.imshow("Optimized ONNX Live Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
