import time
import numpy as np
import re
import yaml
import os
from funasr import AutoModel

# === 读取配置 ===
try:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        local_asr_path = config.get("local_asr_path", "")
except Exception as e:
    print(f"配置文件读取失败: {e}")
    local_asr_path = ""

# === 模型加载 ===
if local_asr_path and os.path.exists(local_asr_path):
    print(f"✅ ASR Core 锁定本地模型: {local_asr_path}")
    model_id = local_asr_path
    local_files_only = True
else:
    print(f"⚠️ 未找到本地路径，使用云端: iic/SenseVoiceSmall")
    model_id = "iic/SenseVoiceSmall"
    local_files_only = False

model = AutoModel(
    model=model_id,
    trust_remote_code=True,
    local_files_only=local_files_only, 
    disable_update=True,
    device="cuda", 
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

def asr_transcribe(input_wav: np.ndarray, config=None) -> str:
    try:
        res = model.generate(
            input=input_wav,
            cache={},
            language="auto",
            use_itn=True,
            batch_size=64
        )
        text = res[0]["text"]
    except Exception as e:
        print(f"推理错误: {e}")
        return ""

    # 清洗 rich text tags
    text = re.sub(r'<\|[^>]+\|>', '', text)
    formatted_text = clean_punctuation(text)
    return formatted_text