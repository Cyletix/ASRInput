# ASRInput  
**A local, real-time speech input system with VAD-based segmentation.**  

ASRInput is a fully local speech-to-text solution designed for Windows. It leverages **Voice Activity Detection (VAD)** for smart segmentation and transcribes speech in real-time with a floating UI. This tool is lightweight, efficient, and requires no internet connection.

---

## 🚀 Features
### 🎙 **Real-time Speech Recognition**
- Runs entirely **offline**, ensuring **privacy**.
- Uses **VAD-based segmentation** for improved transcription accuracy.
- **Low-latency** processing optimized for real-time input.

### 🖥 **Floating UI for Seamless Input**
- **Non-intrusive overlay window** for easy transcription.
- Allows **manual text correction** before confirming input.
- Outputs to the **active application** without switching focus.

### ⚡ **Optimized for Performance**
- **Hardware adaptive** – Works on CPU, but utilizes **GPU acceleration** if available.
- Efficient **audio buffer management** to maintain **low memory footprint**.

### ⌨ **Global Hotkey Support**
- **Quick toggle** for enabling/disabling recognition.
- Customizable hotkeys via `config.yaml`.

### 🔧 **Adaptive Model Optimization**
- **Remembers corrections** for **personalized** transcription.
- Supports **custom ASR models** and fine-tuning.

---

## 📂 Project Structure  
```
ASRInput/
├── src/                    
│   ├── asr_core.py          # Speech recognition core
│   ├── config.py            # Configuration handler
│   ├── config.yaml          # User settings
│   ├── main.py              # Application entry point
│   ├── window.py            # Floating UI implementation
│   ├── worker_thread.py     # Background audio processing thread
├── models/                  # ASR models (if applicable)
├── config/                  
│   └── settings.yaml        # Customizable settings
├── tests/                   # Unit tests
├── requirements.txt         # Project dependencies
└── README.md                # Documentation
```

---

## 🎯 How It Works
1. **Start ASRInput**  
   - Run `python src/main.py`  
   - The floating input window appears.

2. **Speak naturally**  
   - ASRInput listens in real-time and transcribes speech.

3. **Edit if needed**  
   - Modify recognized text before confirming.

4. **Insert text automatically**  
   - Press confirm, and the text will be **typed into the active window**.

---

## 💻 System Requirements
- Windows 10/11  
- Python 3.9+  
- **Optional**: NVIDIA GPU (Recommended for better performance)  

### 🔧 Installation
1. Clone the repository:
   ```sh
   git clone https://github.com/yourusername/ASRInput.git
   cd ASRInput
   ```
2. Create a virtual environment:
   ```sh
   python -m venv venv
   source venv/Scripts/activate  # Windows
   ```
3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

### ▶️ Run the application
```sh
python src/main.py
```

---

## 🛠 Configuration
Modify `config.yaml` to:
- Adjust hotkeys
- Select ASR model
- Optimize VAD parameters

---

## 📌 Roadmap
- ✅ Initial release with **real-time speech input**
- ⏳ Future improvements:
  - 🔹 Custom **language models**
  - 🔹 Advanced **noise filtering**
  - 🔹 Multi-language support

---

## ⚖ License
This project is licensed under the **MIT License**.

---

Now, ASRInput is ready for use! 🚀 Let me know if you need refinements.