import os
import sys
import json
import argparse
import time
from dotenv import load_dotenv

def load_mapping(csv_path):
    import csv
    mapping = {}
    if not os.path.exists(csv_path):
        print(f"[-] Error: Mapping file {csv_path} not found.")
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
                    continue
    except Exception as e:
        print(f"[-] Error reading mapping file: {e}")
        
    print(f"[+] Loaded {len(mapping)} coordinate mappings.")
    return mapping

def send_angles(ser, angles):
    if ser and ser.is_open:
        cmd = ",".join(f"{i}:{v}" for i, v in enumerate(angles))
        ser.write((cmd + "\n").encode())
        print(f" - Sent angles: {cmd}")

def speak_offline(text):
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"[-] Offline TTS failed: {e}")

def speak_text(text, voice_id="EXAVITQu4vr4xnSDxMaL"):
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

def capture_and_detect_objects(camera_index=0, roi_size=0.6, confidence_threshold=0.5, target_class=None):
    """
    Open the camera, capture a frame, run Roboflow object detection, and count the objects.
    Can optionally filter by a specific target class.
    """
    try:
        import cv2
        import supervision as sv
        from inference_sdk import InferenceHTTPClient
    except ImportError as e:
        return {"error": f"Missing required libraries (opencv-python, supervision, or inference-sdk): {e}"}

    # Configuration
    api_url = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")
    api_key = os.getenv("ROBOFLOW_API_KEY")
    model_id = os.getenv("ROBOFLOW_MODEL_ID", "ako_buto/4")
    
    if not api_key:
        return {"error": "Roboflow API Key (ROBOFLOW_API_KEY) not found in environment."}

    print(f"[+] Initializing camera {camera_index}...")
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return {"error": f"Could not open camera with index {camera_index}."}
        
    # Read multiple frames to let auto-exposure adjust
    frame = None
    print("[+] Adjusting camera exposure and capturing frame...")
    for _ in range(8):
        ret, frame = cap.read()
        if not ret:
            break
        time.sleep(0.05)
            
    cap.release()
    
    if frame is None:
        return {"error": "Failed to capture image from camera."}

    print("[+] Sending captured frame to Roboflow Inference API...")
    try:
        client = InferenceHTTPClient(
            api_url=api_url,
            api_key=api_key
        )
        result = client.infer(frame, model_id=model_id)
        detections = sv.Detections.from_inference(result)
        
        # Filter by confidence
        detections = detections[detections.confidence >= confidence_threshold]
        
        # Calculate ROI box
        height, width, _ = frame.shape
        roi_w_full, roi_h = int(width * roi_size), int(height * roi_size)
        x1, y1 = (width - roi_w_full) // 2, (height - roi_h) // 2
        roi_w = int(roi_w_full * 0.75)
        x2, y2 = x1 + roi_w, y1 + roi_h
        
        valid_detections = []
        if len(detections) > 0:
            for i, bbox in enumerate(detections.xyxy):
                cx, cy = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
                in_roi = (x1 <= cx <= x2 and y1 <= cy <= y2)
                class_name = detections.data['class_name'][i]
                conf = detections.confidence[i]
                valid_detections.append({
                    "class": class_name,
                    "confidence": round(float(conf), 2),
                    "in_roi": in_roi
                })
        
        # Filter to only ROI detections as per standard behavior
        roi_only_detections = [d for d in valid_detections if d["in_roi"]]
        
        # Filter by class if target_class is specified
        if target_class:
            target_class_clean = target_class.upper().strip()
            filtered_roi_only_detections = []
            for d in roi_only_detections:
                cls_upper = d["class"].upper()
                # Remove trailing 'S' or do substring checking to match singular/plural
                t_single = target_class_clean[:-1] if target_class_clean.endswith('S') else target_class_clean
                c_single = cls_upper[:-1] if cls_upper.endswith('S') else cls_upper
                if t_single == c_single or t_single in cls_upper or cls_upper in target_class_clean:
                    filtered_roi_only_detections.append(d)
            roi_only_detections = filtered_roi_only_detections
        
        # Group by class to make it easy to summarize
        class_counts = {}
        for d in roi_only_detections:
            cls = d["class"]
            class_counts[cls] = class_counts.get(cls, 0) + 1
            
        summary = {
            "total_objects_in_roi": len(roi_only_detections),
            "total_objects_overall": len(valid_detections),
            "class_counts_in_roi": class_counts
        }
        if target_class:
            summary["filtered_by_class"] = target_class
        
        # Annotate and save the image for debugging
        box_annotator = sv.BoxAnnotator(thickness=2)
        label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1, text_padding=4)
        
        labels = [
            f"{class_name} {confidence:.2f}"
            for class_name, confidence
            in zip(detections.data['class_name'], detections.confidence)
        ]
        annotated_frame = box_annotator.annotate(scene=frame, detections=detections)
        annotated_frame = label_annotator.annotate(scene=annotated_frame, detections=detections, labels=labels)
        
        # Draw ROI Box
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(annotated_frame, "ROI", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        os.makedirs("runs/agentic_arm", exist_ok=True)
        cv2.imwrite("runs/agentic_arm/last_detection.jpg", annotated_frame)
        print("[+] Saved detection debug image to: runs/agentic_arm/last_detection.jpg")
        
        return summary
    except Exception as e:
        print(f"[-] Roboflow inference failed: {e}")
        return {"error": f"Failed to perform object detection: {e}"}

def pick_up_objects(target_class=None, camera_index=0, roi_size=0.6, confidence_threshold=0.5, port=None, baud=115200):
    """
    Open the camera, run object detection for target_class, connect to ESP32 serial,
    and command the arm to pick each target up and drop it in its drop bin.
    If target_class is None, "ALL", or "EVERYTHING", it picks up all supported objects.
    """
    import cv2
    import os
    import time
    import numpy as np
    import serial
    import serial.tools.list_ports
    import supervision as sv
    from inference_sdk import InferenceHTTPClient

    START_POS = [180, 90, 150, 40, 90, 0]
    DROP_ANGLES = {
        "PEANUT": [147, 163, 80, 25, 90, 0],
        "PUMPKIN": [116, 142, 58, 19, 90, 0],
        "SUNFLOWER": [65, 130, 30, 10, 90, 0]
    }

    # Load mapping
    mapping = load_mapping("map.csv")
    if not mapping:
        return {"error": "Could not load coordinate mapping (map.csv is missing or empty)."}

    # Determine if we should pick up all objects
    pick_all = False
    if not target_class or target_class.upper().strip() in ["ALL", "EVERYTHING", "OBJECTS", "ANYTHING", "ALL OBJECTS"]:
        pick_all = True

    matched_class = None
    if not pick_all:
        target_class_clean = target_class.upper().strip()
        if target_class_clean.endswith('S') and target_class_clean not in DROP_ANGLES:
            t_normalized = target_class_clean[:-1]
        else:
            t_normalized = target_class_clean

        for k in DROP_ANGLES.keys():
            if t_normalized == k or k in t_normalized or t_normalized in k:
                matched_class = k
                break

        if not matched_class:
            return {"error": f"Class '{target_class}' is not recognized or has no drop positions defined."}

    # Open camera to capture frame
    print(f"[+] Opening camera {camera_index} for pick and place detection...")
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return {"error": f"Could not open camera index {camera_index}."}

    frame = None
    for _ in range(8):
        ret, frame = cap.read()
        if not ret:
            break
        time.sleep(0.05)
    cap.release()

    if frame is None:
        return {"error": "Failed to capture image from camera."}

    # Run Roboflow inference
    api_url = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")
    api_key = os.getenv("ROBOFLOW_API_KEY")
    model_id = os.getenv("ROBOFLOW_MODEL_ID", "ako_buto/4")

    if not api_key:
        return {"error": "Roboflow API Key (ROBOFLOW_API_KEY) not found in environment."}

    print("[+] Running Roboflow inference to locate targets...")
    try:
        client = InferenceHTTPClient(api_url=api_url, api_key=api_key)
        result = client.infer(frame, model_id=model_id)
        detections = sv.Detections.from_inference(result)
        detections = detections[detections.confidence >= confidence_threshold]
    except Exception as e:
        return {"error": f"Roboflow inference failed: {e}"}

    height, width, _ = frame.shape
    roi_w_full, roi_h = int(width * roi_size), int(height * roi_size)
    x1, y1 = (width - roi_w_full) // 2, (height - roi_h) // 2
    roi_w = int(roi_w_full * 0.75)
    x2, y2 = x1 + roi_w, y1 + roi_h

    targets = []
    for i, bbox in enumerate(detections.xyxy):
        cx, cy = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            class_name = detections.data['class_name'][i].upper()
            
            # Find matching class in DROP_ANGLES
            det_matched_class = None
            for k in DROP_ANGLES.keys():
                c_normalized = class_name[:-1] if class_name.endswith('S') else class_name
                k_normalized = k[:-1] if k.endswith('S') else k
                if c_normalized == k_normalized or k_normalized in class_name or class_name in k:
                    det_matched_class = k
                    break
            
            if not det_matched_class:
                continue

            # If not picking all, check if it matches target_class
            if not pick_all and det_matched_class != matched_class:
                continue

            sx = (cx - x1) * 15 / roi_w
            sy = (cy - y1) * 11 / roi_h
            mx = int(np.clip(round(sx), 1, 14))
            my = int(np.clip(round(sy), 1, 10))
            targets.append({
                "mx": mx,
                "my": my,
                "sx": sx,
                "sy": sy,
                "class_name": det_matched_class,
                "confidence": float(detections.confidence[i])
            })

    if not targets:
        return {"message": f"I analyzed the camera feed but couldn't find any {'objects' if pick_all else matched_class} inside the workspace."}

    print(f"[+] Found {len(targets)} targets to pick.")

    # Connect to serial port
    if not port:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            port = ports[0]
            print(f"[+] Auto-detected serial port: {port}")

    if not port:
        return {"error": "Serial port not specified and none auto-detected. Arm movement skipped.", "targets": targets}

    try:
        print(f"[+] Connecting to ESP32 on {port}...")
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)  # Wait for ESP32 to reset
    except Exception as e:
        return {"error": f"Failed to open serial port {port}: {e}", "targets": targets}

    successful_picks = 0
    failed_picks = []

    # Make sure we start at starting position
    send_angles(ser, START_POS)
    time.sleep(1.5)

    for idx, target in enumerate(targets):
        mx, my = target["mx"], target["my"]
        t_class = target["class_name"]
        print(f"[+] Pick {idx+1}/{len(targets)}: {t_class} at Map coord ({mx}, {my})")

        if (mx, my) in mapping:
            pick_angles = mapping[(mx, my)]
            try:
                # 1. Move to Pick Position (grip open: s5=30)
                send_angles(ser, pick_angles)
                time.sleep(1.5)

                # 2. Close Grip (s5=0)
                send_angles(ser, pick_angles[:5] + [0])
                time.sleep(1.5)

                # 3. Back to Starting Position (grip remains closed)
                send_angles(ser, START_POS)
                time.sleep(1.5)

                # 4. Move to Drop Position based on class (grip closed)
                drop_angles = DROP_ANGLES[t_class]
                send_angles(ser, drop_angles)
                time.sleep(1.5)

                # 5. Open Grip to release (s5=30)
                send_angles(ser, drop_angles[:5] + [30])
                time.sleep(1.5)

                # 6. Back to Starting Position (grip closes)
                send_angles(ser, START_POS)
                time.sleep(1.5)

                successful_picks += 1
            except Exception as ex:
                print(f"[-] Error executing movement: {ex}")
                failed_picks.append((mx, my))
        else:
            print(f"[-] Coordinate ({mx}, {my}) not found in coordinate mapping.")
            failed_picks.append((mx, my))

    ser.close()
    print("[+] Pick and place operations finished. Serial connection closed.")

    result = {
        "target_class": "ALL" if pick_all else matched_class,
        "total_found": len(targets),
        "successful_picks": successful_picks,
        "failed_picks": failed_picks
    }
    return result

def run_agentic_loop(client, args):
    try:
        import speech_recognition as sr
    except ImportError:
        print("[-] Error: speech_recognition library is not installed. Please run: pip install SpeechRecognition")
        sys.exit(1)

    r = sr.Recognizer()
    
    # Initialize message list with system instruction
    messages = [
        {"role": "system", "content": args.system_instruction}
    ]

    # Tool definitions
    tools = [
        {
            "type": "function",
            "function": {
                "name": "count_objects",
                "description": "Use this tool whenever the user asks 'what do you see?', 'how many objects do you see?', 'count the objects', or any similar variation. It captures a live image from the workspace camera, performs object detection, and counts/lists the objects. Can optionally filter to a specific class (e.g. 'peanut', 'pumpkin', 'sunflower').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_class": {
                            "type": "string",
                            "description": "Optional class name to filter by. For example, use 'peanut' if the user asks to count peanuts."
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "pick_up_objects",
                "description": "Command the robotic arm to locate and pick up objects and drop them at their designated drop bins. Can pick up all objects of a specified class (e.g. 'peanut', 'pumpkin', 'sunflower') or pick up all/everything in the workspace if target_class is omitted or set to 'all' or 'everything'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_class": {
                            "type": "string",
                            "description": "Optional class name of objects to pick up. Omit this or set to 'all' / 'everything' to pick up all objects in the workspace."
                        }
                    }
                }
            }
        }
    ]

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
                            
                            messages.append({"role": "user", "content": text})
                            messages.append({"role": "assistant", "content": response_text})
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
                r.pause_threshold = 1.5
                r.non_speaking_duration = 0.5
                try:
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
                    messages.append({"role": "user", "content": prompt})
                    messages.append({"role": "assistant", "content": response_text})
                    continue

                # Add prompt to message history
                messages.append({"role": "user", "content": prompt})

                # Step 3: Call Groq and process agent tool loop
                print("[+] Thinking...")
                try:
                    completion = client.chat.completions.create(
                        model=args.model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto"
                    )
                    
                    response_message = completion.choices[0].message
                    tool_calls = response_message.tool_calls
                    
                    while tool_calls:
                        messages.append(response_message)
                        for tool_call in tool_calls:
                            function_name = tool_call.function.name
                            if function_name == "count_objects":
                                print("[+] Executing count_objects tool...")
                                arguments = {}
                                if tool_call.function.arguments:
                                    try:
                                        parsed = json.loads(tool_call.function.arguments)
                                        if isinstance(parsed, dict):
                                            arguments = parsed
                                    except Exception:
                                        arguments = {}
                                
                                target_class = arguments.get("target_class")
                                print(f"[+] Tool arguments: {arguments}")
                                
                                tool_result = capture_and_detect_objects(
                                    camera_index=args.camera_index,
                                    roi_size=args.roi_size,
                                    confidence_threshold=args.confidence,
                                    target_class=target_class
                                )
                                print(f"[+] Tool output: {tool_result}")
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": function_name,
                                    "content": json.dumps(tool_result)
                                })
                            elif function_name == "pick_up_objects":
                                print("[+] Executing pick_up_objects tool...")
                                arguments = {}
                                if tool_call.function.arguments:
                                    try:
                                        parsed = json.loads(tool_call.function.arguments)
                                        if isinstance(parsed, dict):
                                            arguments = parsed
                                    except Exception:
                                        arguments = {}
                                
                                target_class = arguments.get("target_class")
                                print(f"[+] Tool arguments: {arguments}")
                                
                                tool_result = pick_up_objects(
                                    target_class=target_class,
                                    camera_index=args.camera_index,
                                    roi_size=args.roi_size,
                                    confidence_threshold=args.confidence,
                                    port=args.port,
                                    baud=args.baud
                                )
                                print(f"[+] Tool output: {tool_result}")
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": function_name,
                                    "content": json.dumps(tool_result)
                                })
                        
                        # Get next response from Groq
                        completion = client.chat.completions.create(
                            model=args.model,
                            messages=messages,
                            tools=tools
                        )
                        response_message = completion.choices[0].message
                        tool_calls = response_message.tool_calls
                    
                    response_text = response_message.content
                    messages.append({"role": "assistant", "content": response_text})

                    print("\n" + "=" * 40)
                    print("Bella Response:")
                    print("=" * 40)
                    print(response_text)
                    print("=" * 40 + "\n")
                    
                    if args.speak:
                        speak_text(response_text, voice_id=args.voice)
                        
                except Exception as e:
                    print(f"[-] Request or execution failed: {e}")

    except Exception as e:
        print(f"[-] Error accessing microphone: {e}")
        print("Please ensure your microphone is plugged in and permissions are granted.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Agentic Robotic Arm voice assistant (Bella).")
    parser.add_argument(
        "--system_instruction",
        type=str,
        default="Your name is Bella. You are a super friendly, sweet, cute, and girly AI assistant. The robotic arm is your own body—refer to its actions in the first person (e.g., say 'I've picked up the pumpkins!' instead of 'the robotic arm has picked up the pumpkins'). You have access to tools like object detection via the camera. If the user asks 'what do you see?', 'how many objects do you see?', 'count the objects', or any similar variation, you must call the count_objects tool. Speak in a natural, sweet, warm, and girly tone. Keep your responses ultra-brief (typically one short sentence, max two), avoid any robotic or technical phrasing, and sound enthusiastic and cute!",
        help="System instruction to enforce rules on behavior"
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
        default=True,
        help="Speak the response aloud using ElevenLabs/offline TTS (default: True)"
    )
    parser.add_argument(
        "--no-speak",
        action="store_false",
        dest="speak",
        help="Disable speaking the response aloud"
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="EXAVITQu4vr4xnSDxMaL",
        help="ElevenLabs Voice ID to use (default: Bella [EXAVITQu4vr4xnSDxMaL])"
    )
    parser.add_argument(
        "--camera_index",
        type=int,
        default=0,
        help="OpenCV camera index (default: 0)"
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.5,
        help="Roboflow detection confidence threshold (default: 0.5)"
    )
    parser.add_argument(
        "--roi_size",
        type=float,
        default=0.6,
        help="Size of ROI box as a fraction of frame (0.0 to 1.0, default: 0.6)"
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Serial port for ESP32 (e.g., COM9, default: auto-detect)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200)"
    )
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Get API key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[-] Error: GROQ_API_KEY not found in environment or .env file.")
        print("Please add: GROQ_API_KEY=your_key to your .env file.")
        sys.exit(1)

    print(f"[+] Initializing Groq client using model '{args.model}'...")
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except ImportError:
        print("[-] Error: groq package is not installed. Please run: pip install groq")
        sys.exit(1)

    print("[+] Bella Agentic Robotic Arm Voice Assistant is ready.")
    try:
        run_agentic_loop(client, args)
    except KeyboardInterrupt:
        print("\n[+] Exiting voice assistant. Goodbye!")

if __name__ == "__main__":
    main()
