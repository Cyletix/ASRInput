import os
# 禁止 FunASR 自动检查更新
os.environ["FUNASR_DISABLE_UPDATE"] = "1"

import time as _time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import pyaudio
import yaml
import wave
import logging
from funasr import AutoModel

# 导入核心识别函数
from asr_core import asr_transcribe

# 屏蔽 ModelScope 的繁琐日志
logging.getLogger("modelscope").setLevel(logging.ERROR)

class ASRWorkerThread(QThread):
    # 信号：识别结果 (文本, 音频ID)
    result_ready = pyqtSignal(str, str)
    # 信号：初始化完成 (通知 UI 启用按钮)
    initialized = pyqtSignal()

    def __init__(self, sample_rate=16000, chunk=2048, buffer_seconds=8,
                 device="cuda", config=None, parent=None):
        super().__init__(parent)
        self.sample_rate = sample_rate
        self.chunk = chunk
        self.buffer_seconds = buffer_seconds
        self.device = device
        self.config = config if config else {}
        self.running = True
        self.paused = False

        # === 缓存与参数设置 ===
        self.recognized_audio = {}
        self.max_cache_count = self.config.get("max_cache_count", 20)
        self.cache_clear_interval = self.config.get("cache_clear_interval", 10)
        self.last_cache_clear_time = _time.time()
        
        # VAD 参数：窗口大小 256ms
        self.vad_chunk_ms = 256
        self.vad_chunk_samples = int(self.sample_rate * self.vad_chunk_ms / 1000)
        # 静音阈值 (防止幻觉)
        self.noise_threshold = self.config.get("noise_threshold", 0.002)

        # 创建反馈音频保存目录
        if self.config.get("model_cache_path"):
             os.makedirs(self.config.get("model_cache_path"), exist_ok=True)

        # === 初始化录音流 ===
        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(format=pyaudio.paInt16,
                                   channels=1,
                                   rate=self.sample_rate,
                                   input=True,
                                   frames_per_buffer=self.chunk)
        
        # === 加载 VAD 模型 (支持本地路径) ===
        local_vad_path = self.config.get("local_vad_path", "")
        if local_vad_path and os.path.exists(local_vad_path):
             print(f"✅ Worker 锁定本地 VAD 模型: {local_vad_path}")
             vad_model_id = local_vad_path
             local_files_only = True
        else:
             print(f"⚠️ 未找到本地 VAD 路径，尝试使用云端: speech_fsmn_vad_zh-cn-16k-common-pytorch")
             vad_model_id = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
             local_files_only = False

        try:
            self.model_vad = AutoModel(
                model=vad_model_id,
                model_revision="v2.0.4",
                trust_remote_code=True,
                disable_pbar=True,
                max_end_silence_time=1000,
                disable_update=True,
                device=self.device,
                local_files_only=local_files_only
            )
        except Exception as e:
            print(f"❌ VAD 模型加载失败: {e}")
            # 这里可以做个兜底，但通常加载失败就无法运行了
        
        self.cache_vad = {}

    # === 软暂停：不关闭流，只丢弃数据，防止闪退 ===
    def pause(self):
        self.paused = True
    
    def resume(self):
        self.paused = False
        self.cache_vad = {} # 重置 VAD 状态

    def run(self):
        # 发送初始化完成信号
        self.initialized.emit()

        audio_buffer = np.array([], dtype=np.float32)
        vad_buffer = np.array([], dtype=np.float32)
        vad_buffer_list = [] # 使用 list 暂存，避免频繁 concat 降低性能
        
        offset = 0
        last_vad_beg = -1
        last_vad_end = -1
        last_text = ""
        silence_counter = 0
        required_silence_count = 1

        while self.running:
            # === 暂停状态处理 ===
            if self.paused:
                try:
                    # 必须读出数据并丢弃，防止硬件缓冲区溢出
                    self.stream.read(self.chunk, exception_on_overflow=False)
                except:
                    pass
                _time.sleep(0.02)
                continue

            # === 正常录音 ===
            try:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
            except Exception as e:
                print(f"录音读取错误: {e}")
                continue

            # 转为 float32
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32767.0
            audio_buffer = np.concatenate((audio_buffer, samples))

            # === VAD 处理循环 ===
            while len(audio_buffer) >= self.vad_chunk_samples:
                current_chunk = audio_buffer[:self.vad_chunk_samples]
                audio_buffer = audio_buffer[self.vad_chunk_samples:]
                
                # 放入 VAD 缓冲区
                vad_buffer_list.append(current_chunk)
                # 临时合并用于计算 (优化点：其实可以只在切分时合并，但为了逻辑清晰先这样)
                vad_buffer = np.concatenate(vad_buffer_list) if vad_buffer_list else np.array([], dtype=np.float32)
                
                # VAD 推理
                try:
                    res = self.model_vad.generate(
                        input=current_chunk, 
                        cache=self.cache_vad, 
                        is_final=False, 
                        chunk_size=self.vad_chunk_ms
                    )
                except Exception as e:
                    print(f"VAD 推理出错: {e}")
                    res = []

                if res and "value" in res[0] and len(res[0]["value"]) > 0:
                    vad_segments = res[0]["value"]
                    for segment in vad_segments:
                        if segment[0] > -1: last_vad_beg = segment[0]
                        if segment[1] > -1: last_vad_end = segment[1]
                    
                    # 判断是否有一段完整的语音结束
                    if last_vad_beg > -1 and last_vad_end > -1:
                        silence_counter += 1
                    else:
                        silence_counter = 0

                    # 触发切分识别 (VAD 认为一句话结束了)
                    if silence_counter >= required_silence_count:
                        # 计算起止点
                        beg = int((last_vad_beg - offset) * self.sample_rate / 1000)
                        end = int((last_vad_end - offset) * self.sample_rate / 1000)
                        
                        # 安全检查：确保索引在 buffer 范围内
                        # 关键改动：end 必须 > beg，但不需要 <= buffer.shape[0] (因为我们只切 buffer 里有的)
                        valid_end = min(end, vad_buffer.shape[0])
                        
                        if valid_end > beg:
                            segment_audio = vad_buffer[beg:valid_end]
                            
                            # RMS 静音检测 (防幻觉)
                            rms = np.sqrt(np.mean(segment_audio**2))
                            if rms > self.noise_threshold:
                                try:
                                    text = asr_transcribe(segment_audio)
                                    if text and text.strip() and text != last_text:
                                        last_text = text
                                        audio_id = str(int(_time.time() * 1000))
                                        self.recognized_audio[audio_id] = segment_audio
                                        self.result_ready.emit(text, audio_id)
                                except Exception as e:
                                    print(f"识别错误: {e}")
                            
                            # === 关键补丁：只切掉用到 valid_end 的部分，保留剩下的所有尾巴 ===
                            # 这样下一句的开头绝对不会丢
                            vad_buffer = vad_buffer[valid_end:] 
                            
                            # 必须同步更新 list 缓存，否则下次 concat 又把旧数据拼回来了
                            vad_buffer_list = [vad_buffer] if vad_buffer.size > 0 else []
                            
                            # 更新时间偏移量
                            offset = last_vad_end
                        
                        # 重置状态
                        last_vad_beg = -1
                        last_vad_end = -1
                        silence_counter = 0

            # === 保底逻辑 (强制切分) ===
            # 防止长时间不说话导致内存溢出，或者 VAD 漏检
            vad_buffer = np.concatenate(vad_buffer_list) if vad_buffer_list else np.array([], dtype=np.float32)
            
            if vad_buffer.shape[0] / self.sample_rate >= self.buffer_seconds:
                cut_samples = int(self.buffer_seconds * self.sample_rate)
                segment_audio = vad_buffer[:cut_samples]
                
                # 同样进行 RMS 检测
                rms = np.sqrt(np.mean(segment_audio**2))
                if rms > self.noise_threshold:
                    try:
                        text = asr_transcribe(segment_audio)
                        if text and text.strip() and text != last_text:
                            last_text = text
                            audio_id = str(int(_time.time() * 1000))
                            self.recognized_audio[audio_id] = segment_audio
                            self.result_ready.emit(text, audio_id)
                    except Exception as e:
                         print(f"强制切分识别错误: {e}")
                
                # 移除强制切分的部分
                vad_buffer = vad_buffer[cut_samples:]
                vad_buffer_list = [vad_buffer] if vad_buffer.size > 0 else []
                offset += self.buffer_seconds * 1000
                last_vad_beg = -1
                last_vad_end = -1
                silence_counter = 0

            # === 缓存清理 ===
            if _time.time() - self.last_cache_clear_time > self.cache_clear_interval:
                self.recognized_audio.clear()
                self.last_cache_clear_time = _time.time()
            
            # 降低 CPU 占用
            _time.sleep(0.01)

    def stop(self):
        self.running = False
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.pa.terminate()
        except:
            pass
        self.quit()
        self.wait()

    def save_feedback_audio(self, audio_id):
        """保存反馈音频文件"""
        if audio_id not in self.recognized_audio:
            return ""
        if not os.path.exists("feedback_audio"):
            os.makedirs("feedback_audio")
            
        filename = os.path.join("feedback_audio", f"{audio_id}.wav")
        audio_data = self.recognized_audio[audio_id]
        
        # float32 -> int16
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        try:
            with wave.open(filename, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_int16.tobytes())
            
            # 保存后移除缓存
            self.recognized_audio.pop(audio_id, None)
            return filename
        except Exception as e:
            print(f"保存音频失败: {e}")
            return ""