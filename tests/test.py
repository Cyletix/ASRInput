"""
测试模型加载
"""

from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

model_dir = "SenseVoiceSmall"  # 本地模型目录，相对于你的脚本

model = AutoModel(
    model="iic/SenseVoiceSmall",  # 正确的模型类型
    trust_remote_code=True,
    remote_code=f"{model_dir}/model.py",  # 模型代码路径
    vad_model="fsmn-vad",
    vad_kwargs={"max_single_segment_time": 30000},
    device="cuda:0",
    model_conf={"model_dir": model_dir},  # 模型配置
)

res = model.generate(
    input=f"{model.model_path}/example/en.mp3",  # 音频文件路径
    language="auto",
    use_itn=True,
    batch_size_s=60,
)
text = rich_transcription_postprocess(res[0]["text"])
print(text)