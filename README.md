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


## 项目进度
- [ ] 不转移焦点(多次失败, 重点)
- [ ] 非激活状态下,svg请使用白色线条, 与背景的黑色区分(失败)
- [x] vad分割问题, 错误断句
- [ ] 高性能部分使用C++重构
- [ ] 打包为exe
- [ ] 移植到安卓端

---

## VAD逻辑

### 音频缓冲与 VAD 分割

程序持续从麦克风读取音频数据，并将数据追加到预先分配好的环形缓冲区中。
每次从缓冲区中取出一段固定长度（由 VAD 模型控制的采样点数）的音频数据，传递给 VAD 模型进行检测，获取语音活动段的起始和结束时间。

### 正常分割：基于 VAD 检测

如果 VAD 模型检测到一段有效的语音片段（存在一定的静音段或语音结束），则将该段音频提取出来进行 ASR 识别，并触发输出。


### 强制分割：超时输出

为避免连续说话时没有足够静音导致语音段过长（例如超过设定的最大句子时长 max_sentence_seconds，比如 8 秒或你配置的值），需要引入“超时强制分割”逻辑。
当开始累积一个语音段时，记录一个起始时间（segment_start_time）。
在后续处理中，每次检查当前累积的时间，如果超过 max_sentence_seconds，则强制输出当前缓冲区中已累积的音频数据，并清空缓冲区，这样就能保证一句话不会超过预设时间而影响后续输出。
这种机制同时也能防止长时间没说话而导致缓冲区数据无限增长。
缓存清理

另外，针对已识别但暂存于 recognized_audio 中的音频数据，保持一个最大缓存数量，超过时删除最旧的数据。
定期调用垃圾回收（gc.collect()），以及使用 tracemalloc 输出内存分配快照，方便排查内存问题。