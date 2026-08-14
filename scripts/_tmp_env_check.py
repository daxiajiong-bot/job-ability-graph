import importlib

for m in ["torch", "transformers", "sentence_transformers", "peft", "numpy", "safetensors", "accelerate"]:
    try:
        mod = importlib.import_module(m)
        print(f"{m}: {getattr(mod, '__version__', '?')}")
    except ImportError as e:
        print(f"{m}: NOT INSTALLED")

try:
    import torch
    print("cuda available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("device:", torch.cuda.get_device_name(0), "| mem GB:", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1))
except Exception as e:
    print("torch check failed:", e)
