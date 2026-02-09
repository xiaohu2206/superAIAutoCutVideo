import os
import sys
import traceback


def main() -> int:
    internal = sys.argv[1] if len(sys.argv) > 1 else ""
    if internal:
        sys.path.insert(0, internal)
    os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
    try:
        import torch  # type: ignore

        print("torch_import_ok")
        print("torch_version", getattr(torch, "__version__", None))
        try:
            print("cuda_available", bool(torch.cuda.is_available()))
            print("cuda_device_count", int(torch.cuda.device_count()))
        except Exception as e:
            print("cuda_query_failed", repr(e))
        return 0
    except Exception as e:
        print("torch_import_failed", repr(e))
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

