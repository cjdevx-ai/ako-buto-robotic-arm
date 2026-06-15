import cv2
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="ROI Only Viewer (No Detection)")
    parser.add_argument('--index', type=int, default=0, help='OpenCV camera index (default: 1)')
    parser.add_argument('--roi_size', type=float, default=0.6, help='Size of ROI box as a fraction of frame (0.0 to 1.0)')
    
    args = parser.parse_args()

    # Open the camera
    cap = cv2.VideoCapture(args.index)

    if not cap.isOpened():
        print(f"Error: Could not open camera with index {args.index}")
        return

    print(f"Starting ROI viewer from camera {args.index}...")
    print(f"ROI Size: {args.roi_size}")
    print("Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame.")
            break

        height, width, _ = frame.shape
        
        # Define ROI (Region of Interest) Box centered on the frame
        roi_w_full, roi_h = int(width * args.roi_size), int(height * args.roi_size)
        x1, y1 = (width - roi_w_full) // 2, (height - roi_h) // 2
        
        # Reduce ROI size 1/4 from the right
        roi_w = int(roi_w_full * 0.75)
        x2, y2 = x1 + roi_w, y1 + roi_h
        
        # Crop to ROI
        roi_frame = frame[y1:y2, x1:x2]

        # Display the ROI only
        cv2.imshow("ROI Region Only", roi_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
