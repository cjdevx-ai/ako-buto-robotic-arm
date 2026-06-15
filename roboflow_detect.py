import argparse
import os
import json
from inference_sdk import InferenceHTTPClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def detect_roboflow(image_path, model_id=None, api_key=None, api_url=None):
    """
    Detect objects in an image using Roboflow Inference SDK.
    """
    if not os.path.exists(image_path):
        print(f"Error: Image file '{image_path}' not found.")
        return

    # Use environment variables if not provided
    api_url = api_url or os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")
    api_key = api_key or os.getenv("ROBOFLOW_API_KEY")
    model_id = model_id or os.getenv("ROBOFLOW_MODEL_ID", "ako_buto/4")

    if not api_key:
        print("Error: Roboflow API Key not found. Please set it in .env or via --api_key.")
        return

    # initialize the client
    client = InferenceHTTPClient(
        api_url=api_url,
        api_key=api_key
    )

    # infer on a local image
    result = client.infer(image_path, model_id=model_id)
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Roboflow Object Detection Script")
    parser.add_argument('--image', type=str, required=True, help='Path to the image file')
    parser.add_argument('--model_id', type=str, help='Roboflow model ID (overrides .env)')
    parser.add_argument('--api_key', type=str, help='Roboflow API Key (overrides .env)')
    parser.add_argument('--output', type=str, help='Path to save JSON results')

    args = parser.parse_args()

    result = detect_roboflow(args.image, args.model_id, args.api_key)

    if result:
        print(json.dumps(result, indent=2))
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Results saved to {args.output}")

if __name__ == "__main__":
    main()
