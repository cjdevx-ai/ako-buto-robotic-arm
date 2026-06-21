import os
import sys
import argparse
from dotenv import load_dotenv

def main():
    parser = argparse.ArgumentParser(description="Test ElevenLabs TTS (Text-to-Speech) integration.")
    parser.add_argument(
        "--text",
        type=str,
        default="Hello! This is a test of the ElevenLabs voice integration. The Ako Buto robotic arm is ready to execute commands.",
        help="Text to convert to speech"
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="EXAVITQu4vr4xnSDxMaL",
        help="Voice name or Voice ID to use (default: Bella [EXAVITQu4vr4xnSDxMaL] which is free-tier compatible)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="voice_test_output.mp3",
        help="Path to save the generated audio file"
    )
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Retrieve API key
    api_key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")

    if not api_key:
        print("[-] Error: ELEVENLABS_API_KEY not found in environment or .env file.")
        print("Please add your key to the .env file in the project root:")
        print("ELEVENLABS_API_KEY=your_elevenlabs_api_key_here")
        print("\nGet your API key from the ElevenLabs Dashboard: https://elevenlabs.io")
        sys.exit(1)

    print("[+] ElevenLabs API Key detected.")
    
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save
    except ImportError:
        print("[-] Error: elevenlabs package is not installed. Run: pip install elevenlabs")
        sys.exit(1)

    print(f"[+] Initializing ElevenLabs client with voice '{args.voice}'...")
    client = ElevenLabs(api_key=api_key)

    try:
        print(f"[+] Requesting speech generation for: '{args.text}'")
        
        # Call ElevenLabs API
        audio = client.text_to_speech.convert(
            voice_id=args.voice,
            text=args.text,
            model_id="eleven_multilingual_v2"
        )
        
        # Save generated audio stream to file
        print(f"[+] Saving audio output to: {args.output}")
        save(audio, args.output)
        print("[+] Audio saved successfully!")
        
        # Inform how to listen to it on Windows
        print(f"\n[+] To listen to the generated file on Windows, you can run:")
        print(f"    start {args.output}")
        
    except Exception as e:
        print(f"[-] An error occurred during speech generation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()