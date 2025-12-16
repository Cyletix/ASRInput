import numpy as np
import re
import yaml
import os
import sys
from funasr import AutoModel

# === 路径解析辅助函数 ===
def resolve_model_path(config_path_str):
    """
    逻辑：
    1. 如果 config 为空 -> 返回 None (走云端)
    2. 如果 config 是绝对路径且存在 -> 返回绝对路径
    3. 如果 config 是相对路径 -> 拼接当前程序所在目录 -> 存在则返回，不存在则返回 None
    """
    if not config_path_str:
        return None

    # 获取程序运行的基础路径（兼容 源码运行 和 打包运行）
    if getattr(sys, 'frozen', False):
        #如果是打包后的 EXE/文件夹，base_path 是可执行文件所在目录
        base_path = os.path.dirname(sys.executable)
    else:
        # 如果是 Python 源码运行，base_path 是当前文件所在目录的 上一级 (假设 asr_core.py 在 src/ 下)
        # 你需要根据你的文件结构调整这里，通常指向 main.py 同级或项目根目录
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1. 尝试直接当作绝对路径
    if os.path.isabs(config_path_str) and os.path.exists(config_path_str):
        # print(f"✅ 发现绝对路径模型: {config_path_str}")
        return config_path_str

    # 2. 尝试当作相对路径拼接
    full_path = os.path.join(base_path, config_path_str)
    # 归一化路径分隔符
    full_path = os.path.normpath(full_path)
    
    if os.path.exists(full_path):
        # print(f"✅ 发现本地相对路径模型: {full_path}")
        return full_path
    
    print(f"⚠️ Config指定了 '{config_path_str}' 但路径不存在: {full_path}")
    return None

# === 读取配置 ===
try:
    # 这里的路径读取逻辑也要兼容打包环境
    if getattr(sys, 'frozen', False):
        root_dir = os.path.dirname(sys.executable)
    else:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        
    config_file = os.path.join(root_dir, "config.yaml")
    
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
except Exception as e:
    print(f"配置文件读取失败: {e}")
    config = {}

local_asr_path_cfg = config.get("local_asr_path", "")
disable_update_cfg = config.get("disable_update", True)
vad_factor = config.get("vad_sensitivity_factor", 1.0)
target_lang = config.get("language", "auto")
device_cfg = config.get("device", "cuda")
target_model_name = config.get("model_name", "iic/SenseVoiceSmall")
# === 核心判定逻辑 ===
final_model_path = resolve_model_path(local_asr_path_cfg)

if final_model_path:
    # 情况A: Config 指定了有效路径
    model_id = final_model_path
    local_files_only = True
    print(f"🚀 使用本地模型: {model_id}")
else:
    # 情况B: Config 没写，或者写的路径找不到 -> 走官方云端/默认缓存
    model_id = "iic/SenseVoiceSmall"
    local_files_only = False
    print(f"☁️ 使用云端/缓存模型: {model_id}")

# 1. 确定 VAD 模型的默认阈值（需要根据 FunASR 内部模型确定，此处假设默认值为 0.5）
DEFAULT_VAD_THRESHOLD = 0.5 

# 2. 根据因子计算新的阈值
new_vad_threshold = DEFAULT_VAD_THRESHOLD * vad_factor

# === 加载模型 ===
model = AutoModel(
    model=model_id,
    trust_remote_code=True,
    local_files_only=local_files_only, 
    disable_update= disable_update_cfg,
    device=device_cfg, 
    vad_kwargs={
        "threshold": new_vad_threshold 
        # FSMN-VAD 模型通常使用 "threshold" 或 "vad_threshold" 
        # 实际参数名请以 funasr 库所使用的模型参数为准，通常是 "threshold"。
    }
)

# === [补全] 漏掉的字典定义 (Window.py 需要用到 emo_set) ===
emo_dict = {
    "<|HAPPY|>": "😊", "<|SAD|>": "😔", "<|ANGRY|>": "😡", "<|NEUTRAL|>": "",
    "<|FEARFUL|>": "😰", "<|DISGUSTED|>": "🤢", "<|SURPRISED|>": "😮",
}
event_dict = {
    "<|BGM|>": "🎼", "<|Speech|>": "", "<|Applause|>": "👏", "<|Laughter|>": "😀",
    "<|Cry|>": "😭", "<|Sneeze|>": "🤧", "<|Breath|>": "", "<|Cough|>": "🤧",
}
emoji_dict = {
    "<|nospeech|><|Event_UNK|>": "❓",
    "<|HAPPY|>": "😊", "<|SAD|>": "😔", "<|ANGRY|>": "😡", "<|NEUTRAL|>": "",
    "<|BGM|>": "🎼", "<|Speech|>": "", "<|Applause|>": "👏", "<|Laughter|>": "😀",
    "<|FEARFUL|>": "😰", "<|DISGUSTED|>": "🤢", "<|SURPRISED|>": "😮",
    "<|Cry|>": "😭", "<|EMO_UNKNOWN|>": "", "<|Sneeze|>": "🤧", "<|Breath|>": "",
    "<|Cough|>": "😷", "<|Sing|>": "", "<|Speech_Noise|>": "",
}
lang_dict = {
    "<|zh|>": "<|lang|>", "<|en|>": "<|lang|>", "<|yue|>": "<|lang|>",
    "<|ja|>": "<|lang|>", "<|ko|>": "<|lang|>", "<|nospeech|>": "<|lang|>",
}
# 这就是报错缺少的变量
emo_set = {"😊", "😔", "😡", "😰", "🤢", "😮"}
event_set = {"🎼", "👏", "😀", "😭", "🤧", "😷"}

# === 核心处理函数 ===
def clean_punctuation(text):
    if not text: return ""
    # 去除幻觉 "I"
    text = re.sub(r'^I\s+', '', text) 
    text = re.sub(r'\s+I$', '', text)
    # 标点替换
    text = re.sub(r'[，。,、.]', ' ', text)
    text = re.sub(r'[？?]', '? ', text)
    text = re.sub(r'[！!]', '! ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def asr_transcribe(input_wav: np.ndarray, config_override=None) -> str:
    try:
        # === [修正] 动态参数优先 ===
        # 如果传入了新的配置(比如从菜单切了语言)，就用新的，否则用启动时的默认值
        current_lang = target_lang # 默认值
        use_emoji = False
        
        if config_override:
            current_lang = config_override.get("language", target_lang)
            use_emoji = config_override.get("use_emoji", False)
            
        res = model.generate(
            input=input_wav,
            cache={},
            language=current_lang, # 这里现在是动态的了
            use_itn=True,
            batch_size=64
        )
        text = res[0]["text"]
        
        # Emoji 处理
        if use_emoji:
            for tag, icon in emoji_dict.items():
                text = text.replace(tag, icon)
        
    except Exception as e:
        print(f"推理错误: {e}")
        return ""

    # 清洗 rich text tags
    text = re.sub(r'<\|[^>]+\|>', '', text)
    formatted_text = clean_punctuation(text)
    return formatted_text
