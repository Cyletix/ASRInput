from ctypes import cdll, c_int

libcudnn = cdll.LoadLibrary("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.4/bin/cudnn64_9.dll")

major = c_int()
minor = c_int()
patch = c_int()

libcudnn.cudnnGetVersion.restype = c_int
version = libcudnn.cudnnGetVersion()

print(f"CUDNN Version: {version // 10000}.{version % 10000 // 100}.{version % 100}")


import torch
print(torch.cuda.is_available())
print(torch.cuda.device_count())  # Should be 1 or more if GPU is detected
print(torch.cuda.get_device_name(0)) # Prints the name of the CUDA device