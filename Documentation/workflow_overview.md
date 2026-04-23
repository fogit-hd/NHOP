# NHOP Project - Workflow Invocation & Execution Flow

## Tổng quan
File này ghi chú chi tiết về các workflow chính, cách các workflow được gọi (invoke), các script Python được sử dụng, và luồng chạy của robot khi người dùng ấn Run.

---

## 1. Khi người dùng ấn **Run**

### 1.1. Entry Point
- **Main.xaml** là workflow khởi đầu.

### 1.2. Các bước chính trong Main.xaml
1. **Khởi tạo cấu hình và môi trường:**
   - Đọc file cấu hình (Config.xlsx) qua `Framework/InitAllSettings.xaml`.
   - Gọi `Framework/KillAllProcesses.xaml` để đảm bảo môi trường sạch.
   - Gọi `Framework/InitAllApplications.xaml` để khởi tạo các ứng dụng/phụ trợ cần thiết.
2. **Xử lý transaction:**
   - Gọi `Framework/Process.xaml` để thực hiện nghiệp vụ chính.
     - Trong đó, transaction item (slide) sẽ được truyền vào.
3. **Kết thúc:**
   - Gọi các workflow đóng ứng dụng, dọn dẹp: `Framework/CloseAllApplications.xaml`, `Framework/KillAllProcesses.xaml`.

---

## 2. Luồng chi tiết trong **Process.xaml**
- Gọi `AIInteractivePresenter.xaml` để thực hiện trình bày AI.

---

## 3. Luồng chi tiết trong **AIInteractivePresenter.xaml**
- Gọi `Workflows/AIPresenter/AIPresenter_MainFlow.xaml`.
- Sau khi hoàn thành, gửi email thông báo thành công/thất bại qua `Framework/SendEmailNotification.xaml`.

---

## 4. Luồng chi tiết trong **AIPresenter_MainFlow.xaml**
- Bước 1: Gọi `AIPresenter_InitAndPrepare.xaml` để chuẩn bị config, pipeline, slides.
- Bước 2: Lặp qua từng slide, gọi `AIPresenter_SlideIteration.xaml` để xử lý từng slide.
- Bước 3: Sau khi hoàn thành, có thể gọi các workflow hậu trình bày như `AIPresenter_AfterPresentation.xaml`.

---

## 5. Các script Python được sử dụng & vai trò
- **AIPresenter_InitAndPrepare.xaml**:
  - Chạy các script:
    - `slides_from_pptx.py`: Trích xuất nội dung slide từ file PPTX, tạo file `slides_iterate.tsv`.
    - `pipeline_extract_and_compose.py`: Xử lý pipeline AI, tạo file `gpt_slide_content.txt` (chứa nội dung slide dạng text, mapping với slide).
  - Các file output:
    - `Data/AIPresenter/Temp/slides_iterate.tsv`: Danh sách slide, dùng cho lặp xử lý slide.
    - `Data/AIPresenter/Temp/gpt_slide_content.txt`: Nội dung từng slide.
- **AIPresenter_SlideIteration.xaml**:
  - Chạy các script:
    - `wav_duration_seconds.py`: Tính thời lượng file audio.
    - `build_slide_video.py`: Tạo video cho từng slide từ ảnh và audio.
    - `play_video_blocking.py`, `play_response_audio.py`: Phát video/audio cho slide.
  - Các file output:
    - Video từng slide: `Data/AIPresenter/Temp/slide_segment_{n}.mp4`.
    - Audio narration: `Data/AIPresenter/Temp/narration_{n}.wav`.
- **AIPresenter_AfterPresentation.xaml**:
  - Chạy script phát lại video tổng hợp, hoặc thực hiện các bước hậu trình bày.

---

## 6. Sơ đồ tổng quan luồng chạy

1. **Main.xaml**
    - InitAllSettings
    - KillAllProcesses
    - InitAllApplications
    - **Process.xaml**
        - **AIInteractivePresenter.xaml**
            - **AIPresenter_MainFlow.xaml**
                - **AIPresenter_InitAndPrepare.xaml** (chuẩn bị dữ liệu, chạy pipeline, sinh file slides)
                - **AIPresenter_SlideIteration.xaml** (lặp qua từng slide, tạo video/audio)
                - **AIPresenter_AfterPresentation.xaml** (hậu trình bày)

---

## 7. Tham khảo chi tiết các file/script
- **Scripts Python:**
  - `Data/AIPresenter/Scripts/`
- **Các file output tạm:**
  - `Data/AIPresenter/Temp/`
- **Cấu hình:**
  - `Data/AIPresenter/Config/`

---

## 8. Ghi chú thêm
- Các workflow framework như `SetTransactionStatus`, `RetryCurrentTransaction`, `TakeScreenshot` được gọi trong các tình huống lỗi hoặc trạng thái đặc biệt.
- Email notification được gửi ở cả thành công và thất bại.

---

## 9. Script Python: Mô tả chi tiết theo từng bước workflow

### AIPresenter_InitAndPrepare.xaml
- **1. Đọc cấu hình và thiết lập biến đường dẫn script:**
  - Các activity Assign sẽ thiết lập đường dẫn cho các script như slides_from_pptx.py, pipeline_extract_and_compose.py, open_default_app.py, play_response_audio.py, play_video_blocking.py.
- **2. Tạo file slides_iterate.tsv từ PPTX:**
  - Activity Assign ("Run slides_from_pptx (Shell waits; exit code via .cmd file)")
    - Gọi script: `slides_from_pptx.py` (qua run_python_with_exitfile.cmd)
    - Input: Đường dẫn PPTX, thư mục project
    - Output: `slides_iterate.tsv`, ảnh slide
    - Mục đích: Trích xuất metadata các slide để lặp xử lý về sau.
- **3. Chạy pipeline AI để sinh nội dung từng slide:**
  - Activity Assign ("Run Vision+GPT pipeline (Shell waits; exit code via .cmd file)")
    - Gọi script: `pipeline_extract_and_compose.py` (qua run_python_with_exitfile.cmd)
    - Input: PPTX, config, thư mục project
    - Output: `gpt_slide_content.txt`, `extracted_slides_raw.txt`
    - Mục đích: Sinh nội dung AI cho từng slide.
- **4. (Các bước kiểm tra file, log, delay, load nội dung...)**
  - Không gọi script Python mới, chỉ thao tác file.

### AIPresenter_SlideIteration.xaml
- **1. Chuẩn bị metadata slide:**
  - Các activity Assign lấy thông tin slide, ảnh, nội dung narration từ file đã sinh ở bước trước.
- **2. Nếu có narration:**
  - **a. Gọi ElevenLabs TTS để tạo audio narration:**
    - Activity InvokeWorkflowFile ("Invoke ElevenLabs TTS (slide narration)")
      - Workflow con này sẽ gọi script: `elevenlabs_tts.py` (qua run_python_with_exitfile.cmd)
      - Input: Text narration, API key, voice, output WAV
      - Output: File WAV narration
      - Mục đích: Sinh audio cho slide.
  - **b. Đo thời lượng file WAV narration:**
    - Activity Assign ("Run wav_duration_seconds.py (wait)")
      - Gọi script: `wav_duration_seconds.py`
      - Input: File WAV, output file txt
      - Output: Số giây narration
      - Mục đích: Để căn thời gian phát video/audio.
  - **c. Ghép ảnh và audio thành video segment:**
    - Activity Assign ("ffmpeg: image + WAV → segment (append manifest)")
      - Gọi script: `build_slide_video.py`
      - Input: Ảnh slide, WAV audio, output MP4, ffmpeg, manifest
      - Output: MP4 segment
      - Mục đích: Tạo video cho từng slide.
  - **d. Phát video segment vừa tạo:**
    - Activity StartProcess ("Play slide segment (non-blocking, pyw)")
      - Gọi script: `play_video_blocking.py`
      - Input: File MP4, ffmpeg, pid file
      - Output: Không (chỉ phát video)
      - Mục đích: Trình bày slide.
  - **e. Nếu không tạo được video, fallback phát audio narration:**
    - Activity Assign ("Play narration WAV fallback")
      - Gọi script: `play_response_audio.py`
      - Input: File WAV, ffmpeg
      - Output: Không (chỉ phát audio)
      - Mục đích: Đảm bảo luôn có âm thanh trình bày.
- **3. (Các bước kiểm tra, log, delay, cập nhật trạng thái...)**
  - Không gọi script Python mới.

### AIPresenter_AfterPresentation.xaml
- **1. Nếu có file video tổng hợp:**
  - Activity Assign ("Assign ")
    - Gọi script: `play_video_blocking.py`
    - Input: File MP4 tổng hợp, ffmpeg
    - Output: Không (phát video tổng hợp)
    - Mục đích: Cho phép xem lại toàn bộ trình bày.
- **2. (Các bước log, message box, cập nhật context...)**
  - Không gọi script Python mới.

### Các script tiện ích/hỗ trợ
- **ffplay_locate.py**: Được các script khác gọi nội bộ để xác định vị trí ffplay.exe.
- **run_python_with_exitfile.cmd**: Wrapper để UiPath gọi script Python và kiểm tra trạng thái hoàn thành/lỗi.


