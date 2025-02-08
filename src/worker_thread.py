# worker_thread.py
import os
os.environ["FUNASR_DISABLE_UPDATE"] = "1"  # 禁用更新检查

import time as _time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import pyaudio
from asr_core import asr_transcribe
from funasr import AutoModel
import wave
import re
import logging

logging.getLogger("modelscope").setLevel(logging.ERROR)

class ASRWorkerThread(QThread):
    # 通过 result_ready 信号传递：识别文本和对应音频ID
    result_ready = pyqtSignal(str, str)

    def __init__(self, sample_rate=16000, chunk=2048, buffer_seconds=8,
                 device="cpu", config=None, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.chunk = chunk
        self.buffer_seconds = buffer_seconds
        self.device = device
        self.running = True
        self.config = config

        # 保存识别成功但尚未反馈的音频数据： audio_id -> numpy array
        self.recognized_audio = {}
        self.max_cache_count = self.config.get("max_cache_count", 20) if self.config else 20
        self.cache_clear_interval = self.config.get("cache_clear_interval", 10) if self.config else 10
        self.last_cache_clear_time = _time.time()

        # VAD 参数：以256毫秒为窗口
        self.vad_chunk_ms = 256
        self.vad_chunk_samples = int(self.sample_rate * self.vad_chunk_ms / 1000)

        # 如果配置中指定了模型缓存路径，则设置该目录
        if self.config and self.config.get("model_cache_path"):
            cache_dir = self.config.get("model_cache_path")
            os.makedirs(cache_dir, exist_ok=True)
            os.environ["TRANSFORMERS_CACHE"] = cache_dir

        # 更新检查已禁用

        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(format=pyaudio.paInt16,
                                   channels=1,
                                   rate=self.sample_rate,
                                   input=True,
                                   frames_per_buffer=self.chunk)
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
                                if len(self.recognized_audio) > self.max_cache_count:
                                    oldest_key = next(iter(self.recognized_audio))
                                    del self.recognized_audio[oldest_key]
                            vad_buffer = vad_buffer[end:]
                            offset = last_vad_end
                        last_vad_beg = -1
                        last_vad_end = -1
                        silence_counter = 0

            # 判断 vad_buffer 时长是否已达到阈值
            if len(vad_buffer) / self.sample_rate >= self.buffer_seconds:
                # 如果检测到了有效的分割点，则计算其在缓冲区中的位置（索引）
                if last_vad_end > 0:
                    forced_index = int((last_vad_end - offset) * self.sample_rate / 1000)
                    # 防止计算出无效的索引
                    if forced_index <= 0 or forced_index > len(vad_buffer):
                        forced_index = len(vad_buffer)
                else:
                    forced_index = len(vad_buffer)
                
                segment_audio = vad_buffer[:forced_index]
                try:
                    text = asr_transcribe(segment_audio)
                except Exception as e:
                    text = f"识别错误: {e}"
                if text and text.strip() and text != last_text:
                    last_text = text
                    audio_id = str(int(_time.time() * 1000))
                    self.recognized_audio[audio_id] = segment_audio
                    self.result_ready.emit(text, audio_id)
                
                # 将已经处理的音频从缓冲中剔除，并更新 offset（注意转换单位：samples 到毫秒）
                vad_buffer = vad_buffer[forced_index:]
                offset += (forced_index / self.sample_rate) * 1000
                
                # 重置分割相关变量，等待下一个有效分割
                last_vad_beg = -1
                last_vad_end = -1
                silence_counter = 0

            if _time.time() - self.last_cache_clear_time > self.cache_clear_interval:
                self.recognized_audio.clear()
                self.last_cache_clear_time = _time.time()
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
        self.recognized_audio.pop(audio_id, None)
        return filename
