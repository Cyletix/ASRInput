import os
# 禁止 FunASR 自动检查更新
os.environ["FUNASR_DISABLE_UPDATE"] = "1"

import time as _time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import pyaudio
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
        model_cache_path = self.config.get("model_cache_path")
        if model_cache_path:
            os.makedirs(model_cache_path, exist_ok=True)

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

        # === 核心变量初始化 ===
        # 使用单一的 numpy array 替代 list，避免复杂的拼接逻辑错误
        vad_buffer = np.array([], dtype=np.float32)
        
        offset = 0
        last_vad_beg = -1
        last_vad_end = -1
        last_text = ""
        silence_counter = 0

        pause_delay = self.config.get("vad_pause_delay", 0.8)
        chunk_sec = self.vad_chunk_ms / 1000.0
        
        # 自动计算需要几个块 (至少 1 个)
        required_silence_count = max(1, int(pause_delay / chunk_sec))
        
        # === [关键修正 1] 强制设定最小安全缓冲时间 ==I=
        # 无论配置文件写 2秒 还是 3秒，这里强制至少 6秒 才会触发硬切
        # 这是为了防止 "死循环"（切分->识别卡顿->积压录音->瞬间又满->切分）
        cfg_buffer = self.config.get("buffer_seconds", 6)
        FORCE_CUT_LIMIT = max(float(cfg_buffer), 4.0)
        print(f"✅ 安全缓冲策略: 阈值已修正为 {FORCE_CUT_LIMIT}秒 (配置值: {cfg_buffer}s)")

        while self.running:
            # === 暂停状态处理 ===
            if self.paused:
                try:
                    self.stream.read(self.chunk, exception_on_overflow=False)
                except:
                    pass
                _time.sleep(0.02)
                continue

            # === 录音读取 ===
            try:
                # 这一步可能会因为上次识别卡顿而一次性读出大量数据
                data = self.stream.read(self.chunk, exception_on_overflow=False)
            except Exception as e:
                print(f"录音读取错误: {e}")
                continue

            # 转为 float32
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32767.0
            
            # 直接拼接，逻辑更简单
            vad_buffer = np.concatenate((vad_buffer, samples))

            # === VAD 处理 (处理最新的部分) ===
            # 我们只需要对新进来的数据或者缓冲区末尾进行 VAD 检查
            # 为了性能，我们只把未处理的末尾拿去给 VAD 模型看
            # 但 FunASR VAD 需要连续性，所以这里简化：只在缓冲区积累了一定长度后检测
            
            # 只有当缓冲区足够长时才进行复杂的 VAD 运算，节省 CPU
            if len(vad_buffer) > self.vad_chunk_samples:
                # 为了不重复计算，这里其实应该维护一个指针，但为了逻辑最简，我们只取最后一段
                # 注意：这里仅用于检测静音，不用于切分音频流，切分逻辑在下面
                current_chunk = vad_buffer[-self.vad_chunk_samples:]
                
                try:
                    res = self.model_vad.generate(
                        input=current_chunk, 
                        cache=self.cache_vad, 
                        is_final=False, 
                        chunk_size=self.vad_chunk_ms
                    )
                except Exception as e:
                    res = []

                if res and "value" in res[0] and len(res[0]["value"]) > 0:
                    vad_segments = res[0]["value"]
                    for segment in vad_segments:
                        if segment[0] > -1: last_vad_beg = segment[0]
                        if segment[1] > -1: last_vad_end = segment[1]
                    
                    if last_vad_beg > -1 and last_vad_end > -1:
                        silence_counter += 1
                    else:
                        silence_counter = 0

                    # === [逻辑 A] VAD 自然切分 ===
                    if silence_counter >= required_silence_count:
                        # VAD 认为说话结束了
                        
                        # 识别整个缓冲区
                        rms = np.sqrt(np.mean(vad_buffer**2))
                        if rms > self.noise_threshold:
                            try:
                                text = asr_transcribe(vad_buffer, config_override=self.config)
                                if text and text.strip() and text != last_text:
                                    last_text = text
                                    audio_id = str(int(_time.time() * 1000))
                                    self.result_ready.emit(text, audio_id)
                            except Exception as e:
                                print(f"识别错误: {e}")
                        
                        # VAD 自然结束，清空缓冲区，干干净净
                        vad_buffer = np.array([], dtype=np.float32)
                        self.cache_vad = {} # VAD 缓存也重置
                        last_vad_beg = -1
                        last_vad_end = -1
                        silence_counter = 0

            # === [逻辑 B] 强制切分保护 (防止死锁) ===
            current_duration = len(vad_buffer) / self.sample_rate
            
            if current_duration >= FORCE_CUT_LIMIT:
                print(f"⚠️ 触发强制切分 ({current_duration:.1f}s > {FORCE_CUT_LIMIT}s)")
                
                # 1. 识别当前所有内容
                rms = np.sqrt(np.mean(vad_buffer**2))
                if rms > self.noise_threshold:
                    try:
                        text = asr_transcribe(vad_buffer)
                        if text and text.strip() and text != last_text:
                            last_text = text
                            audio_id = str(int(_time.time() * 1000))
                            self.result_ready.emit(text, audio_id)
                    except Exception as e:
                         print(f"强制切分识别错误: {e}")

                # 2. [关键修正] 重叠回填逻辑
                # 保留最后 1.0 秒作为下一段的开头
                OVERLAP_SAMPLES = int(1.0 * self.sample_rate)
                
                if len(vad_buffer) > OVERLAP_SAMPLES:
                    # 切片：取最后 1秒
                    vad_buffer = vad_buffer[-OVERLAP_SAMPLES:]
                    # !!! 重要 !!! 重置 VAD 缓存，因为音频流被打断了，旧的 VAD 状态可能不匹配
                    self.cache_vad = {} 
                else:
                    # 如果总长度都不够重叠（理论不该发生），清空
                    vad_buffer = np.array([], dtype=np.float32)

                # 重置计数器
                last_vad_beg = -1
                last_vad_end = -1
                silence_counter = 0
            
            # 极短休眠，让出 CPU
            _time.sleep(0.005)

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