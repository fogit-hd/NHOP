# NHOP: New Hire Orientation Program

NHOP is an automation project that runs an orientation session for new hires. A UiPath robot takes PowerPoint decks, works out what each slide says, writes a narration for it, turns the narration into speech, and plays the result slide by slide as a narrated presentation. It was built by NEO Force Batch 5 (OJT) at FPT Software Philippines to cut down on repeated live presentations.

## How it works

1. `Main.xaml` loads settings from `Data/Config.xlsx` and starts the process (based on UiPath's Robotic Enterprise Framework).
2. `AIInteractivePresenter.xaml` runs the AI presenter workflows in `Workflows/AIPresenter/`.
3. Python scripts in `Data/AIPresenter/Scripts/` extract slides from the PPTX files, call OpenAI to describe each slide and compose narration, and call ElevenLabs for text-to-speech.
4. FFmpeg combines each slide image with its audio into a video segment, which is played in turn. A final video can be replayed afterwards.
5. A success or failure email is sent when the run finishes.

## Tech stack

- UiPath Studio / Robot (XAML workflows, REFramework)
- Python 3 (`python-pptx`, `openpyxl`, `Pillow`, `comtypes`, `pywin32`; `tkinter` for popups)
- FFmpeg (`ffmpeg`, `ffplay`, `ffprobe`)
- OpenAI API (slide understanding and narration) and ElevenLabs API (voice)
- Windows batch / PowerShell helper scripts
- Microsoft PowerPoint and Excel on the machine running the robot

## Project structure

```
Main.xaml, AIInteractivePresenter.xaml   # entry points
Framework/        # REFramework workflows (init, process, status, email, cleanup)
Workflows/        # AI/ElevenLabs TTS and AIPresenter/* workflows
Data/
├── Config.xlsx                  # robot settings
└── AIPresenter/
    ├── Config/   # AI settings, prompts, setup guides
    ├── Input/    # PPTX files, slide prompts and mapping sheets
    ├── Output/
    └── Scripts/  # Python helpers
Documentation/    # workflow overview, required applications
Tests/            # UiPath test cases
check_and_install_dependencies.bat
```

## Getting started

This runs on Windows. Required applications are listed in `Documentation/application_required_note.txt`: UiPath Studio, Python 3 (3.11 recommended), FFmpeg, PowerPoint, Excel, plus OpenAI and ElevenLabs accounts.

1. Run `check_and_install_dependencies.bat` to check or install Python packages and other dependencies (it uses winget and PowerShell).
2. Install Python packages if needed: `pip install -r Data/AIPresenter/Scripts/requirements-aipresenter.txt`. See `PYTHON_SETUP.txt` and `ffmpeg_install_guide.txt` in the same folders.
3. Add your own keys in `Data/AIPresenter/Config/ai_settings.json`: `openai_api_key`, `elevenlabs_api_key`, `elevenlabs_voice_id` (see `api_keys_guide.txt`). Do not commit real keys.
4. In `Data/Config.xlsx` (Settings sheet) set the notification email keys: `Email_Sender`, `Email_Recipient`, `Email_SenderPassword`, `Email_SmtpServer`, `Email_SmtpPort` (Gmail: `smtp.gmail.com`, `587`).
5. Put the PPTX files to present in `Data/AIPresenter/Input/pptx_file_here/`. See `pptx_run_order.README.txt` for ordering.
6. Open the project in UiPath Studio and run `Main.xaml`.

## Usage

On run, the robot prepares the slides, generates narration for each one, plays each narrated segment, and emails the result. Intermediate files (slide images, WAV audio, MP4 segments) are written to a temp folder under `Data/AIPresenter/`. More detail is in `Documentation/workflow_overview_en.md`.

## Credits

NEO Force Batch 5, OJT, FPT Software Philippines. Repository owner: [@fogit-hd](https://github.com/fogit-hd).

## License

MIT, see [LICENSE](LICENSE). The license file carries a UiPath copyright line (from the REFramework template).
