import time
import numpy as np
import re
from funasr import AutoModel

# 使用本地模型（前提是环境变量 TRANSFORMERS_CACHE 已正确设置）
model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    # 如支持 local_files_only 参数，可加上 local_files_only=True
    # local_files_only=True
)

# 以下格式化函数取自 server.py 的实现，去掉无用标记
emo_dict = {
    "<|HAPPY|>": "😊",
    "<|SAD|>": "😔",
    "<|ANGRY|>": "😡",
    "<|NEUTRAL|>": "",
    "<|FEARFUL|>": "😰",
    "<|DISGUSTED|>": "🤢",
    "<|SURPRISED|>": "😮",
}
event_dict = {
    "<|BGM|>": "🎼",
    "<|Speech|>": "",
    "<|Applause|>": "👏",
    "<|Laughter|>": "😀",
    "<|Cry|>": "😭",
    "<|Sneeze|>": "🤧",
    "<|Breath|>": "",
    "<|Cough|>": "🤧",
}
emoji_dict = {
    "<|nospeech|><|Event_UNK|>": "❓",
    "<|zh|>": "",
    "<|en|>": "",
    "<|yue|>": "",
    "<|ja|>": "",
    "<|ko|>": "",
    "<|nospeech|>": "",
    "<|HAPPY|>": "😊",
    "<|SAD|>": "😔",
    "<|ANGRY|>": "😡",
    "<|NEUTRAL|>": "",
    "<|BGM|>": "🎼",
    "<|Speech|>": "",
    "<|Applause|>": "👏",
    "<|Laughter|>": "😀",
    "<|FEEARFUL|>": "😰",
    "<|DISGUSTED|>": "🤢",
    "<|SURPRISED|>": "😮",
    "<|Cry|>": "😭",
    "<|EMO_UNKNOWN|>": "",
    "<|Sneeze|>": "🤧",
    "<|Breath|>": "",
    "<|Cough|>": "😷",
    "<|Sing|>": "",
    "<|Speech_Noise|>": "",
    "<|withitn|>": "",
    "<|woitn|>": "",
    "<|GBG|>": "",
    "<|Event_UNK|>": "",
}
lang_dict = {
    "<|zh|>": "<|lang|>",
    "<|en|>": "<|lang|>",
    "<|yue|>": "<|lang|>",
    "<|ja|>": "<|lang|>",
    "<|ko|>": "<|lang|>",
    "<|nospeech|>": "<|lang|>",
}
emo_set = {"😊", "😔", "😡", "😰", "🤢", "😮"}
event_set = {"🎼", "👏", "😀", "😭", "🤧", "😷"}

def format_str_v2(s):
    sptk_dict = {}
    for sptk in emoji_dict:
        sptk_dict[sptk] = s.count(sptk)
        s = s.replace(sptk, "")
    emo = "<|NEUTRAL|>"
    for e in emo_dict:
        if sptk_dict.get(e, 0) > sptk_dict.get(emo, 0):
            emo = e
    for e in event_dict:
        if sptk_dict.get(e, 0) > 0:
            s = event_dict[e] + s
    s = s + emo_dict.get(emo, "")
    for emoji in emo_set.union(event_set):
        s = s.replace(" " + emoji, emoji)
        s = s.replace(emoji + " ", emoji)
    return s.strip()

def format_str_v3(s):
    def get_emo(s):
        return s[-1] if s and s[-1] in emo_set else None
    def get_event(s):
        return s[0] if s and s[0] in event_set else None

    s = s.replace("<|nospeech|><|Event_UNK|>", "❓")
    for lang in lang_dict:
        s = s.replace(lang, "<|lang|>")
    s_list = [format_str_v2(s_i).strip(" ") for s_i in s.split("<|lang|>")]
    new_s = " " + s_list[0]
    cur_ent_event = get_event(new_s)
    for i in range(1, len(s_list)):
        if len(s_list[i]) == 0:
            continue
        if get_event(s_list[i]) == cur_ent_event and get_event(s_list[i]) is not None:
            s_list[i] = s_list[i][1:]
        cur_ent_event = get_event(s_list[i])
        if get_emo(s_list[i]) is not None and get_emo(s_list[i]) == get_emo(new_s):
            new_s = new_s[:-1]
        new_s += s_list[i].strip().lstrip()
    new_s = new_s.replace("The.", " ")
    return new_s.strip()

def asr_transcribe(input_wav: np.ndarray, config=None) -> str:
    start_time = time.time()
    result = model.generate(
        input=input_wav,
        cache={},
        language="auto",
        use_itn=True,
        batch_size=64
    )
    raw_text = result[0]["text"]
    # 根据配置决定是否进行表情和说话人处理
    if config:
        if not config.get("enable_emoji", True):
            # 关闭表情识别时，直接将所有 <|...|> 标签替换为空串
            formatted_text = re.sub(r"<\|[^>]+\|>", "", raw_text).strip()
        else:
            formatted_text = format_str_v3(raw_text)
        if not config.get("enable_speaker", True):
            # 如果禁用说话人识别，则移除可能的说话人标识（假设标识为 "Speaker:"）
            formatted_text = formatted_text.replace("Speaker:", "").strip()
        else:
            # 启用说话人识别时，若文本未包含“Speaker:”则添加默认标签（仅示例）
            if not formatted_text.startswith("Speaker:"):
                formatted_text = "Speaker: " + formatted_text
    else:
        formatted_text = format_str_v3(raw_text)
    return formatted_text
