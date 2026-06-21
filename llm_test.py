import os
import sys
import argparse
from dotenv import load_dotenv

def speak_offline(text):
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"[-] Offline TTS failed: {e}")

def speak_text(text, voice_id="EXAVITQu4vr4xnSDxMaL"):
    import os
    eleven_key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    if eleven_key:
        print(f"[+] ElevenLabs API key found. Generating AI voice (Voice ID: {voice_id})...")
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=eleven_key)
            audio = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_flash_v2_5"  # Use ultra-low latency flash model
            )
            
            # Consume the generator into raw bytes to allow multiple playback attempts or fallback
            audio_bytes = b"".join(audio)
            
            try:
                from elevenlabs import play
                print("[+] Playing audio directly...")
                play(audio_bytes)
            except Exception as play_err:
                print(f"[-] Direct playback failed ({play_err}). Falling back to PowerShell...")
                output_file = "temp_response.mp3"
                with open(output_file, "wb") as f:
                    f.write(audio_bytes)
                
                import subprocess
                abs_path = os.path.abspath(output_file)
                ps_command = f"""
                Add-Type -AssemblyName PresentationCore
                $player = New-Object System.Windows.Media.MediaPlayer
                $player.Open('{abs_path}')
                while ($player.NaturalDuration.HasTimeSpan -ne $true) {{ Start-Sleep -Milliseconds 50 }}
                $player.Play()
                Start-Sleep -Seconds ([math]::Ceiling($player.NaturalDuration.TimeSpan.TotalSeconds))
                """
                subprocess.run(["powershell", "-Command", ps_command], capture_output=True)
                
                # Clean up
                try:
                    os.remove(output_file)
                except Exception:
                    pass
                
        except Exception as e:
            print(f"[-] ElevenLabs generation or playback failed: {e}")
            print("[+] Falling back to offline TTS...")
            speak_offline(text)
    else:
        print("[+] No ElevenLabs API key found. Using offline TTS fallback (pyttsx3)...")
        speak_offline(text)

def run_voice_loop(client, args):
    try:
        import speech_recognition as sr
    except ImportError:
        print("[-] Error: speech_recognition library is not installed. Please run: pip install SpeechRecognition")
        sys.exit(1)
    import time

    r = sr.Recognizer()
    try:
        # Check available microphones
        mics = sr.Microphone.list_microphone_names()
        if not mics:
            print("[-] Error: No microphones found on this system.")
            sys.exit(1)
            
        with sr.Microphone() as source:
            print("[+] Adjusting for ambient noise (1 second)...")
            r.adjust_for_ambient_noise(source, duration=1)
            
            while True:
                # Step 1: Wait for trigger phrase "Bella"
                print("\n[+] Standby mode: Waiting for trigger phrase ('Bella')...")
                trigger_detected = False
                skip_to_standby = False
                
                import random
                flushed_responses = [
                    "Oh! Thank you... that makes me blush!",
                    "Aw, you're making me red! Thank you!",
                    "Hehe, thank you! I'm trying my best!",
                    "Oh gosh... thank you! That is so sweet of you!",
                    "Aw, stooop! You're making me blush!"
                ]
                
                sleep_responses = [
                    "Oki, goodnight! Going to sleep now!",
                    "Goodnight! Sleeping mode activated.",
                    "Oki, time to sleep! Sweet dreams!",
                    "Goodnight! Going to sleep, see you tomorrow!",
                    "Sleeping now, goodnight!"
                ]
                
                while not trigger_detected:
                    try:
                        # Lower thresholds to recognize the short wake phrase immediately
                        r.pause_threshold = 0.4
                        r.non_speaking_duration = 0.4
                        # Listen for a short wake phrase
                        audio = r.listen(source, timeout=None, phrase_time_limit=3)
                        text = r.recognize_google(audio).lower()
                        print(f" (Heard: '{text}')")
                        
                        # Sleep trigger check in standby
                        if "sleep" in text:
                            print(f"[+] Sleep command detected ({text})!")
                            try:
                                import winsound
                                winsound.Beep(1568, 150)
                                winsound.Beep(1318, 150)
                                winsound.Beep(1047, 500)
                            except Exception:
                                pass
                            
                            response_text = random.choice(sleep_responses)
                            print("\n" + "=" * 40)
                            print("Bella Response (sleeping):")
                            print("=" * 40)
                            print(response_text)
                            print("=" * 40 + "\n")
                            if args.speak:
                                speak_text(response_text, voice_id=args.voice)
                            sys.exit(0)
                        
                        # Easter egg check in standby
                        if "good girl" in text:
                            print(f"[+] Easter egg detected ({text})!")
                            try:
                                import winsound
                                winsound.Beep(1047, 250)
                                winsound.Beep(1318, 250)
                                winsound.Beep(1568, 250)
                                winsound.Beep(2093, 750)
                            except Exception:
                                pass
                            
                            response_text = random.choice(flushed_responses)
                            print("\n" + "=" * 40)
                            print("Bella Response (flushed):")
                            print("=" * 40)
                            print(response_text)
                            print("=" * 40 + "\n")
                            if args.speak:
                                speak_text(response_text, voice_id=args.voice)
                            
                            skip_to_standby = True
                            break
                            
                        if "bella" in text:
                            print(f"[+] Trigger phrase detected ({text})!")
                            try:
                                import winsound
                                # Play a beautiful 1.5-second C-major arpeggio chime
                                winsound.Beep(1047, 250)
                                winsound.Beep(1318, 250)
                                winsound.Beep(1568, 250)
                                winsound.Beep(2093, 750)
                            except Exception:
                                pass
                            trigger_detected = True
                    except sr.UnknownValueError:
                        # Noise or untranslatable speech, keep waiting
                        continue
                    except sr.RequestError as e:
                        print(f"[-] Speech recognition service error: {e}")
                        time.sleep(1)
                    except Exception as e:
                        print(f"[-] Error while listening for trigger: {e}")
                        time.sleep(0.5)

                if skip_to_standby:
                    continue

                # Step 2: Record the actual user instruction/prompt
                print("[+] Now recording your instruction... (Speak now! Wait for a 1.5-second pause to end recording)")
                # Set pause_threshold to 1.5 seconds to wait for a 1.5-second pause
                r.pause_threshold = 1.5
                r.non_speaking_duration = 0.5
                try:
                    # Wait up to 10 seconds for user to start speaking their instruction
                    audio = r.listen(source, timeout=10, phrase_time_limit=None)
                    print("[+] Transcribing voice instruction...")
                    prompt = r.recognize_google(audio)
                    print(f"[+] You said: {prompt}")
                except sr.WaitTimeoutError:
                    print("[-] Timeout waiting for instruction. Returning to standby mode...")
                    continue
                except sr.UnknownValueError:
                    print("[-] Could not understand the instruction. Returning to standby mode...")
                    continue
                except sr.RequestError as e:
                    print(f"[-] Speech recognition service error: {e}")
                    continue

                # Sleep trigger check in instruction
                if "sleep" in prompt.lower():
                    try:
                        import winsound
                        winsound.Beep(1568, 150)
                        winsound.Beep(1318, 150)
                        winsound.Beep(1047, 500)
                    except Exception:
                        pass
                    
                    response_text = random.choice(sleep_responses)
                    print("\n" + "=" * 40)
                    print("Bella Response (sleeping):")
                    print("=" * 40)
                    print(response_text)
                    print("=" * 40 + "\n")
                    if args.speak:
                        speak_text(response_text, voice_id=args.voice)
                    sys.exit(0)

                # Easter egg check in instruction
                if "good girl" in prompt.lower():
                    response_text = random.choice(flushed_responses)
                    print("\n" + "=" * 40)
                    print("Bella Response (flushed):")
                    print("=" * 40)
                    print(response_text)
                    print("=" * 40 + "\n")
                    if args.speak:
                        speak_text(response_text, voice_id=args.voice)
                    continue

                # Step 3: Send prompt to Groq and speak response
                print(f"[+] Sending prompt: {repr(prompt)}")
                print("[+] Waiting for response...")
                try:
                    completion = client.chat.completions.create(
                        model=args.model,
                        messages=[
                            {"role": "system", "content": args.system_instruction},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    response_text = completion.choices[0].message.content

                    print("\n" + "=" * 40)
                    print("Groq Response:")
                    print("=" * 40)
                    print(response_text)
                    print("=" * 40 + "\n")
                    
                    if args.speak:
                        speak_text(response_text, voice_id=args.voice)
                        
                except Exception as e:
                    print(f"[-] Request failed: {e}")
                    
    except Exception as e:
        print(f"[-] Error accessing microphone: {e}")
        print("Please ensure your microphone is plugged in and permissions are granted.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Groq LLM voice chat test.")
    parser.add_argument(
        "--prompt",
        type=str,
        default="What is your name?",
        help="Prompt to send to the model"
    )
    parser.add_argument(
        "--system_instruction",
        type=str,
        default="Your name is Bella. You are a super friendly, sweet, cute, and girly AI assistant. Speak in a natural, sweet, warm, and girly tone. Keep your responses ultra-brief (typically one short sentence, max two), use contractions (like 'I'm', 'can't'), avoid any robotic or technical phrasing, and sound enthusiastic and cute!",
        help="System instruction to enforce rules on behavior (default: warm, cute, girly, ultra-brief, names Bella)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="llama-3.3-70b-versatile",
        help="Groq Model ID to use (default: llama-3.3-70b-versatile)"
    )
    parser.add_argument(
        "--speak",
        action="store_true",
        help="Speak the response aloud using ElevenLabs (online) or pyttsx3 (offline fallback)"
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="EXAVITQu4vr4xnSDxMaL",
        help="ElevenLabs Voice ID to use (default: Bella [EXAVITQu4vr4xnSDxMaL])"
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Capture voice input from microphone as the prompt"
    )
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()

    # Get API key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[-] Error: GROQ_API_KEY not found in environment or .env file.")
        print("Please add: GROQ_API_KEY=your_key to your .env file.")
        print("Get a free key from: https://console.groq.com")
        sys.exit(1)

    print("[+] GROQ API Key detected (obfuscated: ...{})".format(api_key[-4:] if len(api_key) > 4 else ""))
    print(f"[+] Initializing Groq client using model '{args.model}'...")

    try:
        from groq import Groq
    except ImportError:
        print("[-] Error: groq package is not installed. Please run: pip install groq")
        sys.exit(1)
        
    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        print(f"[-] Request failed: {e}")
        sys.exit(1)

    if args.listen:
        try:
            run_voice_loop(client, args)
        except KeyboardInterrupt:
            print("\n[+] Exiting voice assistant. Goodbye!")
    else:
        prompt = args.prompt
        print(f"[+] Sending prompt: {repr(prompt)}")
        print("[+] Waiting for response...")
        try:
            completion = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": args.system_instruction},
                    {"role": "user", "content": prompt}
                ]
            )
            response_text = completion.choices[0].message.content

            print("\n" + "=" * 40)
            print("Groq Response:")
            print("=" * 40)
            print(response_text)
            print("=" * 40 + "\n")
            
            if args.speak:
                speak_text(response_text, voice_id=args.voice)
                
            print("[+] Test successful!")

        except Exception as e:
            print(f"[-] Request failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()