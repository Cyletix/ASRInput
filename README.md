# ASRInput  
**A local, real-time speech input system with VAD-based segmentation.**  

ASRInput is a fully local speech-to-text solution designed for Windows. It leverages **Voice Activity Detection (VAD)** for smart segmentation and transcribes speech in real-time with a floating UI. This tool is lightweight, efficient, and requires no internet connection.

![](assets/voice-chat_11401399.png)

---

## 🚀 Features
### 🎙 **Real-time Speech Recognition**
- Runs entirely **offline**, ensuring **privacy**.
- Uses **VAD-based segmentation** for improved transcription accuracy.
- **Low-latency** processing optimized for real-time input.
- **Multi-language support**: Chinese, English, Japanese, Cantonese, Korean, and auto-detection.

### 🖥 **Dual UI Modes**
- **Full Mode**: Complete interface with text editing and manual send
- **Minimal Mode**: Compact floating button for direct speech-to-text
- **Non-intrusive overlay window** for seamless integration
- **Transparent background** with rounded corners for modern look

### ⚡ **Optimized for Performance**
- **Hardware adaptive** – Works on CPU, but utilizes **GPU acceleration** if available.
- Efficient **audio buffer management** to maintain **low memory footprint**.
- **VAD sensitivity tuning** (0.5-2.0) for different noise environments.

### ⌨ **Global Hotkey Support**
- **Quick toggle** for enabling/disabling recognition (Ctrl+Shift+H).
- **Hide window** with ESC key.
- Customizable hotkeys via `config.yaml`.

### 🔧 **Adaptive Configuration**
- **Remembers corrections** for **personalized** transcription.
- Supports **custom ASR models** and fine-tuning.
- **System tray integration** with comprehensive settings menu.
- **Real-time configuration updates** without restart.

### 🌐 **Language Support**
- **Chinese (zh)** - Default language
- **English (en)** - Full support
- **Japanese (ja)** - Japanese transcription
- **Cantonese (yue)** - Cantonese dialect
- **Korean (ko)** - Korean language
- **Auto-detection** - Automatic language detection

---

## 📂 Project Structure  
```
ASRInput/
├── src/
│   ├── asr_core.py          # ASR engine & Emoji processing
│   ├── config.yaml          # User configuration (Critical)
│   ├── main.py              # Entry point
│   ├── window.py            # GUI & Tray implementation
│   └── worker_thread.py     # Audio capture & VAD logic
├── models/                  # Local models directory
│   └── iic/                 # SenseVoiceSmall & FSMN-VAD
├── log/                     # Runtime logs
├── assets/                  # (Optional) Icon assets
│   ├── audio-melody-music-38-svgrepo-com.svg  # App Icon
│   ├── ms_mic_active.svg        # Active State Icon
│   ├── ms_mic_inactive.svg      # Inactive State Icon
├── requirements.txt         # Dependencies
└── README.md                # Documentation
```

---

## 🎯 How It Works
1. **Start ASRInput**  
   - Run `python src/main.py`  
   - The floating input window appears in system tray.

2. **Choose Mode**  
   - **Full Mode**: Edit text before sending
   - **Minimal Mode**: Direct speech-to-text with compact UI

3. **Speak naturally**  
   - ASRInput listens in real-time and transcribes speech.
   - VAD automatically segments speech based on pauses.

4. **Configure on the fly**  
   - Use system tray menu to adjust:
     - Language selection
     - VAD sensitivity
     - Buffer duration
     - Auto-send delay
     - UI mode

5. **Insert text automatically**  
   - Text is automatically typed into active window.
   - Manual editing available in Full Mode.

---

## 💻 System Requirements
- **OS**: Windows 10/11  
- **Python**: 3.9-3.11
- **Memory**: 4GB RAM minimum
- **Storage**: 1.02GB for models
- **Optional**: NVIDIA GPU (Recommended for better performance)  

### 🔧 Installation
1. Clone the repository:
   ```sh
   git clone https://github.com/Cyletix/ASRInput.git
   cd ASRInput
   ```
2. Create a virtual environment:
   ```sh
   python -m venv .asrinput
   .asrinput\Scripts\Activate.ps1
   python.exe -m pip install --upgrade pip
   ```
3. **Install PyTorch (Select one based on your GPU)**
   
   **Option A**: For Modern GPU Support CUDA 12.x(Recommended)
   ```sh
   pip install torch torchvision torchaudio --index-url [https://download.pytorch.org/whl/cu124](https://download.pytorch.org/whl/cu124)
   ```
   **Option B**: For Older GPUs Support CUDA 11.x
   ```
   pip install torch torchvision torchaudio --index-url [https://download.pytorch.org/whl/cu118](https://download.pytorch.org/whl/cu118)
   ```
   Option C: CPU Only (No NVIDIA GPU)
   ```sh
   pip install torch torchvision torchaudio
   ```

4. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
5. Download models (first run will auto-download):
   - ASR Model: SenseVoiceSmall
   - VAD Model: speech_fsmn_vad_zh-cn-16k-common-pytorch

### ▶️ Run the application
```sh
.asrinput\Scripts\Activate.ps1
python src/main.py
```

---

## 🛠 Configuration
Modify `src/config.yaml` to customize:

### Core Settings
```yaml
language: zh                    # Language: zh, en, ja, yue, ko, auto
device: cuda                   # cuda or cpu
sample_rate: 16000             # Audio sample rate
buffer_seconds: 6              # Audio buffer duration
vad_sensitivity_factor: 0.2    # VAD sensitivity (0.5-2.0)
auto_send_delay: 3             # Auto-send delay in seconds
```

### Model Paths
```yaml
local_asr_path: "models\\iic\\SenseVoiceSmall"
local_vad_path: "models\\iic\\speech_fsmn_vad_zh-cn-16k-common-pytorch"
```

### VAD Optimization
```yaml
vad_pause_delay: 0.8           # Pause detection delay in seconds
noise_threshold: 0.002         # Silence threshold
```

---

## 🎮 Usage Tips

### System Tray Controls
- **Right-click tray icon** for full settings menu
- **Double-click tray icon** to show/hide window
- **Toggle service**: Enable/disable recognition
- **Switch UI mode**: Full ↔ Minimal
- **Adjust settings**: Language, sensitivity, buffers

### Hotkeys
- `Ctrl+Shift+H`: Toggle window visibility
- `ESC`: Hide window and pause recognition
- Click microphone button to pause/resume

### Modes
- **Full Mode**: For editing and manual control
- **Minimal Mode**: For direct, distraction-free input

---

## 🔄 Recent Updates (v2.0)

### New Features
- **Dual UI Modes**: Full and Minimal mode switching
- **Multi-language Support**: 6 language options with auto-detection
- **VAD Sensitivity Control**: Fine-tune for different environments
- **Enhanced System Tray**: Complete configuration menu
- **Improved Audio Processing**: Better VAD segmentation and silence detection

### Technical Improvements
- Refactored configuration loading and model path resolution
- Optimized VAD sensitivity settings
- Enhanced error handling and logging
- Modern UI with transparent backgrounds and rounded elements
- Better memory management and garbage collection

### Bug Fixes
- Fixed audio segmentation logic
- Resolved UI state synchronization issues
- Improved focus handling
- Enhanced model loading reliability

---

## 📌 Roadmap
- ✅ Initial release with real-time speech input
- ✅ Dual UI modes (Full/Minimal)
- ✅ Multi-language support
- ✅ VAD sensitivity tuning
- ⏳ Future improvements:
  - 🔹 Custom language models
  - 🔹 Advanced noise filtering
  - 🔹 Export/import configurations
  - 🔹 Plugin system for custom actions
  - 🔹 Cross-platform support (Linux/macOS)

---

## ⚖ License
This project is licensed under the **MIT License**.

---

## 🐛 Troubleshooting

### Common Issues
1. **No audio input**: Check microphone permissions and device selection
2. **High CPU usage**: Reduce buffer size or switch to GPU
3. **Model download failures**: Check internet connection or set local paths
4. **UI not responding**: Restart application or check system resources

### Logs
- Recognition logs are saved in `log/` directory
- Check logs for detailed error information
- Enable debug mode in config for more verbose logging

---

## 🤝 Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

Now, ASRInput is ready for use! 🚀 Let me know if you need refinements.
