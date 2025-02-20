import os
os.environ["FUNASR_DISABLE_UPDATE"] = "1"  # 禁用更新检查

import time as _time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import pyaudio
from asr_core import asr_transcribe
from funasr import AutoModel
import wave
import logging

logging.getLogger("modelscope").setLevel(logging.ERROR)

class ASRWorkerThread(QThread):
    # 通过 result_ready 信号传递识别文本和对应音频ID
    result_ready = pyqtSignal(str, str)
    # 初始化完成信号，用于通知 UI 层停止加载动画
    initialized = pyqtSignal()

    def __init__(self, sample_rate=8192, chunk=1024, buffer_seconds=8,
                 device="cuda", config=None, parent=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        # 读取配置参数
        self.sample_rate = self.config.get("sample_rate", sample_rate)
        self.chunk = self.config.get("chunk", chunk)
        self.buffer_seconds = self.config.get("buffer_seconds", buffer_seconds)
        self.device = self.config.get("device", device)
        self.running = True

        # 根据反馈模式设置不同的处理路径，避免循环中每次判断
        self.accept_feedback = self.config.get("accept_feedback", False)
        if self.accept_feedback:
            self.recognized_audio = {}
        else:
            self.recognized_audio = None
        # 定时清理缓存参数，仅在反馈模式下有意义
        self.cache_clear_interval = self.config.get("cache_clear_interval", 10)
        self.last_cache_clear_time = _time.time()
        # 根据反馈模式设置处理函数
        if self.accept_feedback:
            self.process_result = self._process_result_feedback
        else:
            self.process_result = self._process_result_no_feedback

        # VAD 参数，从配置中读取（单位毫秒），默认512ms
        self.vad_chunk_ms = self.config.get("vad_interval", 512)
        self.vad_chunk_samples = int(self.sample_rate * self.vad_chunk_ms / 1000)

        # 噪声阈值
        self.noise_threshold = self.config.get("noise_threshold", 0.01)

        # 如果配置中指定了模型缓存路径，则创建该目录
        if self.config.get("model_cache_path"):
            cache_dir = self.config.get("model_cache_path")
            os.makedirs(cache_dir, exist_ok=True)

        # 打开录音流
        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(format=pyaudio.paInt16,
                                   channels=1,
                                   rate=self.sample_rate,
                                   input=True,
                                   frames_per_buffer=self.chunk)

        # 获取 VAD 模型参数，从环境变量中读取 VAD_MODEL_DIR
        vad_model_param = os.environ.get("VAD_MODEL_DIR")
        if os.path.exists(vad_model_param):
            local_files_only = True
            disable_update = True
            trust_remote_code = False
        else:
            vad_model_param = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
            local_files_only = False
            disable_update = False
            trust_remote_code = True

        # 可通过配置调整 VAD 模型版本，默认 "v2.0.4"
        model_revision = self.config.get("vad_model_revision", "v2.0.4")

        self.model_vad = AutoModel(
            model=vad_model_param,
            local_files_only=local_files_only,
            disable_update=disable_update,
            trust_remote_code=trust_remote_code,
            model_revision=model_revision,
            disable_pbar=True,
            max_end_silence_time=1000,
            device=self.device
        )
        self.cache_vad = {}

        # 暂停标志
        self.paused = False

    def _process_result_feedback(self, segment_audio):
        """反馈模式下：存储音频并定时清理缓存，返回生成的 audio_id"""
        audio_id = str(int(_time.time() * 1000))
        self.recognized_audio[audio_id] = segment_audio
        if _time.time() - self.last_cache_clear_time > self.cache_clear_interval:
            self.recognized_audio.clear()
            self.last_cache_clear_time = _time.time()
        return audio_id

    def _process_result_no_feedback(self, segment_audio):
        """非反馈模式下，不存储音频，返回空 audio_id"""
        return ""

    def run(self):
        self.initialized.emit()
        # 使用列表存储采集到的音频数据，避免频繁使用 np.concatenate
        audio_buffer_list = []
        # 用于存储待处理的 VAD 数据块
        vad_buffer_list = []

        offset = 0
        last_vad_beg = -1
        last_vad_end = -1
        last_text = ""
        silence_counter = 0
        required_silence_count = 1  # 可加入配置调整

        while self.running:
            if self.paused:
                _time.sleep(0.1)
                continue
            try:
                # 读取音频数据，使用 exception_on_overflow=False 防止异常
                data = self.stream.read(self.chunk, exception_on_overflow=False)
            except Exception as e:
                print(f"录音读取错误: {e}")
                continue

            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32767.0
            audio_buffer_list.append(samples)
            total_length = sum(arr.shape[0] for arr in audio_buffer_list)

            # 当缓冲区内采样点达到一个 VAD 分块时进行处理
            while total_length >= self.vad_chunk_samples:
                needed = self.vad_chunk_samples
                collected = []
                collected_len = 0
                while audio_buffer_list and collected_len < needed:
                    arr = audio_buffer_list.pop(0)
                    collected.append(arr)
                    collected_len += arr.shape[0]
                segment = np.concatenate(collected)
                current_chunk = segment[:needed]
                remainder = segment[needed:]
                if remainder.size > 0:
                    audio_buffer_list.insert(0, remainder)
                total_length = sum(arr.shape[0] for arr in audio_buffer_list)

                # 将当前块添加到 VAD 缓冲区
                vad_buffer_list.append(current_chunk)
                vad_buffer = np.concatenate(vad_buffer_list) if vad_buffer_list else np.array([], dtype=np.float32)

                # 调用 VAD 模型处理当前块
                res = self.model_vad.generate(
                    input=current_chunk,
                    cache=self.cache_vad,
                    is_final=False,
                    chunk_size=self.vad_chunk_ms
                )
                if res and "value" in res[0] and len(res[0]["value"]) > 0:
                    vad_segments = res[0]["value"]
                    for segment_val in vad_segments:
                        if segment_val[0] > -1:
                            last_vad_beg = segment_val[0]
                        if segment_val[1] > -1:
                            last_vad_end = segment_val[1]
                    if last_vad_beg > -1 and last_vad_end > -1:
                        silence_counter += 1
                    else:
                        silence_counter = 0

                    if silence_counter >= required_silence_count:
                        beg = int((last_vad_beg - offset) * self.sample_rate / 1000)
                        end = int((last_vad_end - offset) * self.sample_rate / 1000)
                        if end > beg and end <= vad_buffer.shape[0]:
                            segment_audio = vad_buffer[beg:end]
                            rms = np.sqrt(np.mean(segment_audio**2))
                            if rms < self.noise_threshold:
                                vad_buffer = vad_buffer[end:]
                                vad_buffer_list = [vad_buffer] if vad_buffer.size > 0 else []
                                offset = last_vad_end
                                last_vad_beg = -1
                                last_vad_end = -1
                                silence_counter = 0
                                continue
                            try:
                                text = asr_transcribe(segment_audio, self.config)
                            except Exception as e:
                                err_str = str(e)
                                if "choose a window size 0" in err_str:
                                    text = ""
                                else:
                                    text = f"识别错误: {e}"
                            # 处理识别结果，如果文本变化且非空
                            if text and text.strip() and text != last_text:
                                last_text = text
                                # 根据不同模式调用不同处理函数（避免每轮 if 判断）
                                audio_id = self.process_result(segment_audio)
                                self.result_ready.emit(text, audio_id)
                            # 清除已处理的 VAD 缓冲区数据
                            vad_buffer = vad_buffer[end:]
                            vad_buffer_list = [vad_buffer] if vad_buffer.size > 0 else []
                            offset = last_vad_end
                        last_vad_beg = -1
                        last_vad_end = -1
                        silence_counter = 0

            _time.sleep(0.05)  # 调整 sleep 时间，平衡 CPU 占用和实时性

    def stop(self):
        self.running = False
        try:
            if self.stream.is_active():
                self.stream.stop_stream()
        except Exception:
            pass
        self.stream.close()
        self.pa.terminate()
        self.quit()

    def save_feedback_audio(self, audio_id):
        if self.recognized_audio is None or audio_id not in self.recognized_audio:
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

    def pause(self):
        if not self.paused:
            self.paused = True
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
            except Exception as e:
                print("暂停时出错:", e)
            print("语音识别已暂停")

    def resume(self):
        if self.paused:
            self.paused = False
            try:
                self.stream.start_stream()
            except Exception as e:
                print("恢复时出错:", e)
            print("语音识别已恢复")
