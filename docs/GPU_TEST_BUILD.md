# GPU 本地测试版

- 支持浏览选择任意位置、任意名称的 GGUF 翻译模型，推荐 Hy-MT2 系列。
- 模型选择保存后自动重新加载；无效文件不会覆盖现有设置。
- 主界面支持拖动缩放、最大化、宽屏双栏与译文展开阅读。
- 使用 Vulkan GPU 后端，未启用 GPU 的构建环境会停止 GPU 打包。

解压后运行 `PopTrans.exe`，在设置的“翻译模型”中选择已有模型并保存。
未包含翻译模型；未选择本地模型时保留原版默认模型的下载行为。
配置文件、运行日志、构建环境和本地路径不随测试包分发。

## 构建

使用 Python 3.12 环境安装 `backend/requirements-gpu-vulkan.txt`，
然后依次运行 `scripts/build_all.bat` 与 `scripts/build_ai_engine_gpu.bat`。
后一个脚本会用 GPU 引擎覆盖默认引擎。
