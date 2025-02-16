import sys
import os
import yaml
from PyQt6.QtWidgets import QApplication

def load_config(config_path):
    if not os.path.exists(config_path):
        print("[Warning] config file not found, using defaults.")
        return {
            "model_name": "large",
            "language": "zh",
            "device": "cuda",
            "buffer_seconds": 1.5,
            "step_seconds": 0.5,
            "remove_trailing_period": True,
            "trailing_punctuation": "",
            "punctuation_mode": "half",
            "model_cache_path": "models",
            "max_cache_count": 20,
            "cache_clear_interval": 10,
            "recognize_emoji": False,
            "recognize_speaker": False,
            "accept_feedback": False,
            "vad_interval": 256,
            "noise_threshold": 0.01,
            "max_sentence_seconds": 4,
            "chunk": 1024
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def prepare_models():
    """
    在项目根目录下拼凑本地模型的路径：
      - asr 模型路径为 "models/iic/SenseVoiceSmall"
      - vad 模型路径为 "models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
    若对应目录不存在，则返回在线模型标识，AutoModel 会自动下载（同时环境变量 TRANSFORMERS_CACHE 已设置为项目中的 models 目录）。
    此外，将结果分别写入环境变量 ASR_MODEL_DIR 和 VAD_MODEL_DIR 以便后续模块调用。
    """
    current_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(current_dir, ".."))
    models_dir = os.path.join(project_root, "models")
    
    asr_local_dir = os.path.join(models_dir, "iic", "SenseVoiceSmall")
    vad_local_dir = os.path.join(models_dir, "iic", "speech_fsmn_vad_zh-cn-16k-common-pytorch")
    
    if os.path.exists(asr_local_dir):
        asr_model_param = asr_local_dir
    else:
        print("[Info] Local ASR model not found, will attempt to download from online.")
        asr_model_param = "iic/SenseVoiceSmall"
        
    if os.path.exists(vad_local_dir):
        vad_model_param = vad_local_dir
    else:
        print("[Info] Local VAD model not found, will attempt to download from online.")
        vad_model_param = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
    
    # 将拼凑好的路径写入环境变量，供各模块调用
    os.environ["ASR_MODEL_DIR"] = asr_model_param
    os.environ["VAD_MODEL_DIR"] = vad_model_param
    
    return asr_model_param, vad_model_param, project_root

# 加载配置文件（若不存在则使用默认配置）
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config_dict = load_config(config_path)

# 统一拼凑本地模型路径（或在线标识），并将结果加入到配置中
asr_model_dir, vad_model_dir, project_root = prepare_models()
config_dict["asr_model_dir"] = asr_model_dir
config_dict["vad_model_dir"] = vad_model_dir

# 设置 TRANSFORMERS_CACHE 为项目根目录下的 models（绝对路径），便于下载模型时保存到指定目录
models_abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", config_dict.get("model_cache_path", "models")))
os.environ["TRANSFORMERS_CACHE"] = models_abs_path
print("TRANSFORMERS_CACHE set to:", os.environ["TRANSFORMERS_CACHE"])

# 下载模型时保存到指定目录models
os.environ["MODELSCOPE_CACHE"] = config_path


from window import ModernUIWindow

def main():
    app = QApplication(sys.argv)
    main_window = ModernUIWindow(config_dict)
    main_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
