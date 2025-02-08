# worker_thread.py
import time as _time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import pyaudio
from asr_core import asr_transcribe
from funasr import AutoModel
import os
import wave

class ASRWorkerThread(QThread):
    # result_ready 信号传递：识别文本和一个音频ID
    result_ready = pyqtSignal(str, str)

    def __init__(self, sample_rate=16000, chunk=2048, buffer_seconds=8, device="cpu", config=None, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.chunk = chunk
        self.buffer_seconds = buffer_seconds
        self.device = device
        self.running = True
        self.config = config

        # 缓存识别成功但未反馈的音频数据，字典：audio_id -> numpy array
        self.recognized_audio = {}

        # 定义 VAD 参数：以 256 毫秒为一个处理窗口
        self.vad_chunk_ms = 256
        self.vad_chunk_samples = int(self.sample_rate * self.vad_chunk_ms / 1000)

        # 如果配置中定义了模型缓存路径，则将该路径作为缓存目录
        if self.config and self.config.get("model_cache_path"):
            cache_dir = self.config.get("model_cache_path")
            os.makedirs(cache_dir, exist_ok=True)
            os.environ["TRANSFORMERS_CACHE"] = cache_dir

        # 检查模型更新（伪代码，可根据实际 API 扩展）
        self.update_model_if_needed()

        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(format=pyaudio.paInt16,
                                   channels=1,
                                   rate=self.sample_rate,
                                   input=True,
                                   frames_per_buffer=self.chunk)
        # 增加 trust_remote_code 参数，解决远程加载模块报错
        self.model_vad = AutoModel(
            model="fsmn-vad",
            model_revision="v2.0.4",
            trust_remote_code=True,
            disable_pbar=True,
            max_end_silence_time=1000,
            disable_update=True,
            device=self.device
        )
        self.cache_vad = {}

    def update_model_if_needed(self):
        # 此处为伪代码：检查更新并下载最新模型到指定目录
        print("检查模型更新...")
        force_update = False
        if self.config:
            force_update = self.config.get("force_update", False)
        if force_update:
            print("强制更新模型...")
            # 此处可调用模型下载 API
        else:
            print("使用缓存模型（如果存在）")

    def run(self):
        audio_buffer = np.array([], dtype=np.float32)
        vad_buffer = np.array([], dtype=np.float32)
        offset = 0
        last_vad_beg = -1
        last_vad_end = -1
        last_text = ""
        silence_counter = 0
        required_silence_count = 1

        while self.running:
            try:
                data = self.stream.read(self.chunk)
            except Exception as e:
                print(f"录音读取错误: {e}")
                continue

            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32767.0
            audio_buffer = np.concatenate((audio_buffer, samples))

            while len(audio_buffer) >= self.vad_chunk_samples:
                current_chunk = audio_buffer[:self.vad_chunk_samples]
                audio_buffer = audio_buffer[self.vad_chunk_samples:]
                vad_buffer = np.concatenate((vad_buffer, current_chunk))
                
                res = self.model_vad.generate(
                    input=current_chunk,
                    cache=self.cache_vad,
                    is_final=False,
                    chunk_size=self.vad_chunk_ms
                )
                if res and "value" in res[0] and len(res[0]["value"]) > 0:
                    vad_segments = res[0]["value"]
                    for segment in vad_segments:
                        if segment[0] > -1:
                            last_vad_beg = segment[0]
                        if segment[1] > -1:
                            last_vad_end = segment[1]
                    if last_vad_beg > -1 and last_vad_end > -1:
                        silence_counter += 1
                    else:
                        silence_counter = 0

                    if silence_counter >= required_silence_count:
                        beg = int((last_vad_beg - offset) * self.sample_rate / 1000)
                        end = int((last_vad_end - offset) * self.sample_rate / 1000)
                        if end > beg and end <= len(vad_buffer):
                            segment_audio = vad_buffer[beg:end]
                            try:
                                text = asr_transcribe(segment_audio)
                            except Exception as e:
                                text = f"识别错误: {e}"
                            if text and text.strip() and text != last_text:
                                last_text = text
                                # 生成音频ID，使用时间戳
                                audio_id = str(int(_time.time()*1000))
                                # 缓存该语音数据，只有用户反馈时才保存到磁盘
                                self.recognized_audio[audio_id] = segment_audio
                                self.result_ready.emit(text, audio_id)
                            vad_buffer = vad_buffer[end:]
                            offset = last_vad_end
                        last_vad_beg = -1
                        last_vad_end = -1
                        silence_counter = 0
            _time.sleep(0.01)

    def stop(self):
        self.running = False
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()
        self.quit()

    def save_feedback_audio(self, audio_id):
        """将对应音频缓存保存为 wav 文件，并返回文件名。"""
        if audio_id not in self.recognized_audio:
            return ""
        if not os.path.exists("feedback_audio"):
            os.makedirs("feedback_audio")
        filename = os.path.join("feedback_audio", f"{audio_id}.wav")
        audio_data = self.recognized_audio[audio_id]
        # 将 float32 转为 int16 数据
        audio_int16 = (audio_data * 32767).astype(np.int16)
        wf = wave.open(filename, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(self.sample_rate)
        wf.writeframes(audio_int16.tobytes())
        wf.close()
        return filename
