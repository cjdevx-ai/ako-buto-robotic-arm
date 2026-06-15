# Seed Object Detection

A simple Python script to detect objects from images or videos using a YOLO model (`best.pt`).

## Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/seed_obj_detection.git
    cd seed_obj_detection
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Add your model**:
    Place your `best.pt` file in the project root directory.

## Usage

Run the detection script by specifying the source image(s) or video:

```bash
python detect.py --source path/to/your/image.jpg
```

Options:
- `--model`: Path to the `.pt` model file (default: `best.pt`).
- `--source`: Path to an image, directory, or video.
- `--output`: Directory to save results (default: `runs/detect`).

## Results

Results are automatically saved to `runs/detect/predict` by default.
