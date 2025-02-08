# worker_thread.py
import time as _time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import pyaudio
from asr_core import asr_transcribe
from funasr import AutoModel
import os
import wave
import logging

# 降低 funasr 日志输出级别，减少无关提示
logging.getLogger("modelscope").setLevel(logging.ERROR)

class ASRWorkerThread(QThread):
    # result_ready 信号传递：识别文本和对应音频ID
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

        # 设置最大缓存条数，默认20（可在配置中调整）
        self.max_cache_count = self.config.get("max_cache_count", 20) if self.config else 20

        # 定义 VAD 参数，以256毫秒为处理窗口
        self.vad_chunk_ms = 256
        self.vad_chunk_samples = int(self.sample_rate * self.vad_chunk_ms / 1000)

        # 如果配置中定义了模型缓存路径，则设置为缓存目录
        if self.config and self.config.get("model_cache_path"):
            cache_dir = self.config.get("model_cache_path")
            os.makedirs(cache_dir, exist_ok=True)
            os.environ["TRANSFORMERS_CACHE"] = cache_dir

        # 移除更新检查，避免因更新卡顿或识别失败
        # self.update_model_if_needed()  <-- 已删除

        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(format=pyaudio.paInt16,
                                   channels=1,
                                   rate=self.sample_rate,
                                   input=True,
                                   frames_per_buffer=self.chunk)
        # 增加 trust_remote_code 参数，避免远程加载报错
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
                                audio_id = str(int(_time.time() * 1000))
                                self.recognized_audio[audio_id] = segment_audio
                                self.result_ready.emit(text, audio_id)
                                # 如果缓存超过最大值，则删除最旧的条目
                                if len(self.recognized_audio) > self.max_cache_count:
                                    oldest_key = next(iter(self.recognized_audio))
                                    del self.recognized_audio[oldest_key]
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
        if audio_id not in self.recognized_audio:
            return ""
        if not os.path.exists("feedback_audio"):
            os.makedirs("feedback_audio")
        filename = os.path.join("feedback_audio", f"{audio_id}.wav")
        audio_data = self.recognized_audio[audio_id]
        audio_int16 = (audio_data * 32767).astype(np.int16)
        wf = wave.open(filename, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(self.sample_rate)
        wf.writeframes(audio_int16.tobytes())
        wf.close()
        # 保存反馈后，从缓存中删除对应数据
        self.recognized_audio.pop(audio_id, None)
        return filename
