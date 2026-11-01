"""Prepare the selected Python environment's CUDA DLLs for a portable build."""
import importlib.util
from pathlib import Path
import shutil


def prepare():
    spec = importlib.util.find_spec("llama_cpp")
    if not spec or not spec.origin:
        raise RuntimeError("Install backend/requirements-gpu-cuda.txt first")
    library = Path(spec.origin).parent / "lib"
    if not (library / "ggml-cuda.dll").is_file():
        raise RuntimeError("The selected llama-cpp-python package is not a CUDA build")
    for package in ("nvidia.cublas", "nvidia.cuda_runtime"):
        try:
            module = importlib.util.find_spec(package)
        except ModuleNotFoundError:
            module = None
        if module:
            for location in module.submodule_search_locations or []:
                for file in Path(location).rglob("*.dll"):
                    shutil.copy2(file, library / file.name)
    for name in ("cudart64_12.dll", "cublas64_12.dll", "cublasLt64_12.dll"):
        if not (library / name).is_file():
            raise RuntimeError(f"Missing CUDA runtime dependency: {name}")
    import llama_cpp
    if not llama_cpp.llama_supports_gpu_offload():
        raise RuntimeError("CUDA GPU offload is unavailable")
    print("CUDA dependencies ready")


if __name__ == "__main__":
    prepare()
