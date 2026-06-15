import cv2
import os
import argparse
from ultralytics import YOLO

def detect_objects(model_path, source, output_dir='runs/detect'):
    """
    Detect objects in images or a video using a YOLO model.
    """
    # Load the model
    if not os.path.exists(model_path):
        print(f"Error: Model file '{model_path}' not found.")
        return

    model = YOLO(model_path)

    # Perform inference
    results = model(source, save=True, project=output_dir, name='predict', exist_ok=True)

    print(f"Inference complete. Results saved to {output_dir}/predict")

def main():
    parser = argparse.ArgumentParser(description="YOLOv8 Object Detection Script")
    parser.add_argument('--model', type=str, default='best.pt', help='Path to the .pt model file')
    parser.add_argument('--source', type=str, required=True, help='Path to an image, directory, or video')
    parser.add_argument('--output', type=str, default='runs/detect', help='Directory to save results')

    args = parser.parse_args()

    detect_objects(args.model, args.source, args.output)

if __name__ == "__main__":
    main()
