# download_model.py
import os
from funasr import AutoModel

MODEL_NAME = "iic/SenseVoiceSmall"
MODEL_CACHE_PATH = "models"

def download_model():
    os.makedirs(MODEL_CACHE_PATH, exist_ok=True)
    # 简单判断 models 目录是否为空，若非空则认为已下载（根据实际情况可进一步检查）
    if os.listdir(MODEL_CACHE_PATH):
        print("检测到模型缓存目录不为空，跳过下载。")
        return
    os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_PATH
    print("开始下载模型...")
    model = AutoModel(
         model=MODEL_NAME,
         trust_remote_code=True,
    )
    print("模型下载完成。")

if __name__ == '__main__':
    download_model()
