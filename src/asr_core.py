import time
import numpy as np
import re
import os
from funasr import AutoModel

# 直接从环境变量获取 ASR 模型参数（由 main.py 中 prepare_models 写入）
asr_model_param = os.environ.get("ASR_MODEL_DIR")
if os.path.exists(asr_model_param):
    local_files_only=True
    disable_update=True
    trust_remote_code=False

else:
    asr_model_param = "iic/SenseVoiceSmall"
    local_files_only=False
    disable_update=False
    trust_remote_code=True

model = AutoModel(
    model=asr_model_param,
    local_files_only=local_files_only,
    disable_update=disable_update,
    trust_remote_code=trust_remote_code,
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
    if config:
        if not config.get("recognize_emoji", True):
            formatted_text = re.sub(r"<\|[^>]+\|>", "", raw_text).strip()
        else:
            formatted_text = format_str_v3(raw_text)
        # 无论是否启用识别说话人，都不在文本中添加 "Speaker:" 前缀
        formatted_text = formatted_text.replace("Speaker:", "").strip()
    else:
        formatted_text = format_str_v3(raw_text)
    return formatted_text
