import time
import numpy as np
import re
import yaml
import os
from funasr import AutoModel

# === Load Configuration ===
try:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        local_asr_path = config.get("local_asr_path", "")
except Exception as e:
    print(f"Config load error: {e}")
    local_asr_path = ""

# === Model Loading Logic ===
if local_asr_path and os.path.exists(local_asr_path):
    print(f"✅ ASR Core using LOCAL model: {local_asr_path}")
    model_id = local_asr_path
    local_files_only = True
else:
    print(f"⚠️ Local path not found or empty. Using CLOUD model: iic/SenseVoiceSmall")
    model_id = "iic/SenseVoiceSmall"
    local_files_only = False

model = AutoModel(
    model=model_id,
    trust_remote_code=True,
    local_files_only=local_files_only,
    disable_update=True,
    device="cuda", 
)

def clean_punctuation(text):
    if not text: return ""
    # Remove hallucinated "I"
    text = re.sub(r'^I\s+', '', text) 
    text = re.sub(r'\s+I$', '', text)
    # Standardize punctuation
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
        print(f"Inference Error: {e}")
        return ""

    text = re.sub(r'<\|[^>]+\|>', '', text)
    formatted_text = clean_punctuation(text)
    return formatted_text