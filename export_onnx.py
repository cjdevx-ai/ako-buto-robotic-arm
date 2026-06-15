import os
from roboflow import Roboflow
from ultralytics import YOLO
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def export_to_onnx():
    api_key = os.getenv("ROBOFLOW_API_KEY")
    model_id = os.getenv("ROBOFLOW_MODEL_ID") # e.g., "ako_buto/4"
    
    if not api_key or not model_id:
        print("Error: API Key or Model ID not found in .env")
        return

    # Split model_id into workspace and project
    parts = model_id.split('/')
    if len(parts) != 2:
        print(f"Error: Invalid model_id format '{model_id}'. Expected 'workspace/project_id'")
        return
    
    project_id = parts[0]
    version = parts[1]

    # Initialize Roboflow
    rf = Roboflow(api_key=api_key)
    
    # Access the project and version
    # Note: Roboflow's API structure can vary, but this is the standard way for YOLOv8/v9/v11
    try:
        project = rf.workspace().project(project_id)
        model = project.version(int(version)).model
        
        print(f"Downloading model weights for {model_id}...")
        # This usually downloads a .pt file for YOLO models
        model_path = model.download("pt") 
        
        # Look for the .pt file in the downloaded directory
        pt_file = None
        for root, dirs, files in os.walk(model_path.location):
            for file in files:
                if file.endswith(".pt"):
                    pt_file = os.path.join(root, file)
                    break
            if pt_file: break
            
        if not pt_file:
            print("Error: Could not find .pt file in the downloaded model.")
            return

        print(f"Found weights at: {pt_file}")
        print("Exporting to ONNX...")
        
        # Load with Ultralytics and export
        yolo_model = YOLO(pt_file)
        onnx_path = yolo_model.export(format="onnx")
        
        print(f"Success! Model exported to: {onnx_path}")
        
    except Exception as e:
        print(f"Error during export: {e}")
        print("\nNote: If this fails, it might be because the model type is not directly exportable via this script.")
        print("You can also export to ONNX directly from the Roboflow Dashboard:")
        print(f"https://app.roboflow.com/{model_id}")

if __name__ == "__main__":
    export_to_onnx()
