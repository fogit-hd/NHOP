# NHOP Project - Workflow Invocation & Execution Flow (English)

## Overview
This file documents in detail the main workflows, how they are invoked, which Python scripts are used, and the robot's execution flow when the user clicks Run.

---

## 1. When the user clicks **Run**

### 1.1. Entry Point
- **Main.xaml** is the starting workflow.

### 1.2. Main steps in Main.xaml
1. **Initialize configuration and environment:**
   - Read the configuration file (Config.xlsx) via `Framework/InitAllSettings.xaml`.
   - Call `Framework/KillAllProcesses.xaml` to ensure a clean environment.
   - Call `Framework/InitAllApplications.xaml` to initialize required applications/services.
2. **Transaction processing:**
   - Call `Framework/Process.xaml` to execute the main business logic.
     - The transaction item (slide) is passed in.
3. **Cleanup:**
   - Call workflows to close applications and clean up: `Framework/CloseAllApplications.xaml`, `Framework/KillAllProcesses.xaml`.

---

## 2. Details in **Process.xaml**
- Calls `AIInteractivePresenter.xaml` to perform the AI presentation.

---

## 3. Details in **AIInteractivePresenter.xaml**
- Calls `Workflows/AIPresenter/AIPresenter_MainFlow.xaml`.
- After completion, sends a success/failure notification email via `Framework/SendEmailNotification.xaml`.

---

## 4. Details in **AIPresenter_MainFlow.xaml**
- Step 1: Calls `AIPresenter_InitAndPrepare.xaml` to prepare config, pipeline, and slides.
- Step 2: Iterates through each slide, calling `AIPresenter_SlideIteration.xaml` to process each slide.
- Step 3: After finishing, may call post-presentation workflows like `AIPresenter_AfterPresentation.xaml`.

---

## 5. Python scripts used & their roles
- **AIPresenter_InitAndPrepare.xaml**:
  - Runs scripts:
    - `slides_from_pptx.py`: Extracts slide content from PPTX, creates `slides_iterate.tsv`.
    - `pipeline_extract_and_compose.py`: Runs the AI pipeline, creates `gpt_slide_content.txt` (text content for slides, mapped to slides).
  - Output files:
    - `Data/AIPresenter/Temp/slides_iterate.tsv`: List of slides, used for iteration.
    - `Data/AIPresenter/Temp/gpt_slide_content.txt`: Content for each slide.
- **AIPresenter_SlideIteration.xaml**:
  - Runs scripts:
    - `wav_duration_seconds.py`: Calculates audio file duration.
    - `build_slide_video.py`: Creates video for each slide from image and audio.
    - `play_video_blocking.py`, `play_response_audio.py`: Plays video/audio for the slide.
  - Output files:
    - Slide video: `Data/AIPresenter/Temp/slide_segment_{n}.mp4`.
    - Narration audio: `Data/AIPresenter/Temp/narration_{n}.wav`.
- **AIPresenter_AfterPresentation.xaml**:
  - Runs scripts to replay the final video or perform post-presentation steps.

---

## 6. High-level workflow diagram

1. **Main.xaml**
    - InitAllSettings
    - KillAllProcesses
    - InitAllApplications
    - **Process.xaml**
        - **AIInteractivePresenter.xaml**
            - **AIPresenter_MainFlow.xaml**
                - **AIPresenter_InitAndPrepare.xaml** (prepare data, run pipeline, generate slides)
                - **AIPresenter_SlideIteration.xaml** (iterate slides, create video/audio)
                - **AIPresenter_AfterPresentation.xaml** (post-presentation)

---

## 7. Reference for files/scripts
- **Python Scripts:**
  - `Data/AIPresenter/Scripts/`
- **Temporary output files:**
  - `Data/AIPresenter/Temp/`
- **Configuration:**
  - `Data/AIPresenter/Config/`

---

## 8. Additional notes
- Framework workflows like `SetTransactionStatus`, `RetryCurrentTransaction`, `TakeScreenshot` are called in error or special status situations.
- Email notifications are sent on both success and failure.

---

## 9. Python Scripts: Step-by-Step Workflow Integration

### AIPresenter_InitAndPrepare.xaml
- **1. Read configuration and set script paths:**
  - Assign activities set paths for scripts like slides_from_pptx.py, pipeline_extract_and_compose.py, open_default_app.py, play_response_audio.py, play_video_blocking.py.
- **2. Generate slides_iterate.tsv from PPTX:**
  - Assign activity ("Run slides_from_pptx (Shell waits; exit code via .cmd file)")
    - Calls script: `slides_from_pptx.py` (via run_python_with_exitfile.cmd)
    - Input: PPTX path, project folder
    - Output: `slides_iterate.tsv`, slide images
    - Purpose: Extract slide metadata for later iteration.
- **3. Run AI pipeline to generate slide content:**
  - Assign activity ("Run Vision+GPT pipeline (Shell waits; exit code via .cmd file)")
    - Calls script: `pipeline_extract_and_compose.py` (via run_python_with_exitfile.cmd)
    - Input: PPTX, config, project folder
    - Output: `gpt_slide_content.txt`, `extracted_slides_raw.txt`
    - Purpose: Generate AI narration/content for each slide.
- **4. (Other steps: file checks, logs, delay, load content...)**
  - No new Python scripts called, only file operations.

### AIPresenter_SlideIteration.xaml
- **1. Prepare slide metadata:**
  - Assign activities extract slide info, image, narration from files generated above.
- **2. If narration exists:**
  - **a. Call ElevenLabs TTS to generate narration audio:**
    - InvokeWorkflowFile activity ("Invoke ElevenLabs TTS (slide narration)")
      - This child workflow calls: `elevenlabs_tts.py` (via run_python_with_exitfile.cmd)
      - Input: Narration text, API key, voice, output WAV
      - Output: WAV narration file
      - Purpose: Generate audio for the slide.
  - **b. Measure narration WAV duration:**
    - Assign activity ("Run wav_duration_seconds.py (wait)")
      - Calls script: `wav_duration_seconds.py`
      - Input: WAV file, output txt
      - Output: Narration duration (seconds)
      - Purpose: To time video/audio playback.
  - **c. Mux image and audio into video segment:**
    - Assign activity ("ffmpeg: image + WAV → segment (append manifest)")
      - Calls script: `build_slide_video.py`
      - Input: Slide image, WAV audio, output MP4, ffmpeg, manifest
      - Output: MP4 segment
      - Purpose: Create video for each slide.
  - **d. Play the generated video segment:**
    - StartProcess activity ("Play slide segment (non-blocking, pyw)")
      - Calls script: `play_video_blocking.py`
      - Input: MP4 file, ffmpeg, pid file
      - Output: None (just plays video)
      - Purpose: Present the slide.
  - **e. If video creation fails, fallback to playing narration audio:**
    - Assign activity ("Play narration WAV fallback")
      - Calls script: `play_response_audio.py`
      - Input: WAV file, ffmpeg
      - Output: None (just plays audio)
      - Purpose: Ensure narration is always played.
- **3. (Other steps: checks, logs, delay, state updates...)**
  - No new Python scripts called.

### AIPresenter_AfterPresentation.xaml
- **1. If a final presentation video exists:**
  - Assign activity ("Assign ")
    - Calls script: `play_video_blocking.py`
    - Input: Final MP4, ffmpeg
    - Output: None (plays final video)
    - Purpose: Allow user to review the full presentation.
- **2. (Other steps: logs, message box, context updates...)**
  - No new Python scripts called.

### Utility/Support Scripts
- **ffplay_locate.py**: Called internally by other scripts to locate ffplay.exe.
- **run_python_with_exitfile.cmd**: Wrapper for UiPath to call Python scripts and check completion/error status.
