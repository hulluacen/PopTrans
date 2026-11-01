# CUDA 本地构建

CUDA 与 Vulkan 使用同一套应用代码和术语逻辑，仅 llama-cpp-python 后端不同。
Windows CUDA 版使用 llama-cpp-python 0.3.36 的 CUDA 12.4 构建，适用于兼容 CUDA 12 的 NVIDIA 显卡和驱动。

在独立的 Python 3.12 环境中安装 backend/requirements-gpu-cuda.txt，然后运行 scripts/build_ai_engine_cuda.bat。
该脚本使用当前 python，也可通过 PY_CMD 指定 Python 命令。依赖安装需事先完成，构建脚本不下载组件。
prepare_cuda.py 将所选 Python 环境的 cuBLAS、CUDA Runtime DLL 复制到该环境的 llama_cpp/lib，检查后再构建。
不会安装完整 CUDA Toolkit 或更改系统 PATH。

CUDA 引擎输出到 dist-ai-CUDA/ai_engine.exe。将其与已构建的 PopTrans.exe、translate-ui.exe、图标、RapidOCR 模型和许可证放到独立目录。
发行包须包含 llama-cpp-python 的许可证、NVIDIA cuBLAS 与 CUDA Runtime 的许可证；不要携带用户设置、词库、日志或翻译模型。
主程序可命名为 PopTrans-CUDA.exe，压缩包名称以 -CUDA.zip 结尾，与 -Vulkan.zip 分开。

运行时 /health 的 device_info.backend 会报告 cuda、vulkan 或 cpu；actual 应为 gpu 才表示使用 GPU 路径。
仅编译成功或支持 GPU 卸载的布尔值不能替代实际运行验证。
比较速度时保持模型、量化、GPU 卸载层数和输入一致，避免同时运行两个版本，并区别首次启动、首次翻译、后续翻译及翻译缓存命中。
