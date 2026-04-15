"""GPU allocation; TF vs PyTorch process isolation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Framework(str, Enum):
    PYTORCH = "pytorch"
    TENSORFLOW = "tensorflow"


@dataclass
class GPUManager:
    """Reserve devices per framework; spawn isolated workers for TF."""

    cuda_visible_devices: str | None = None

    def with_pytorch_devices(self) -> dict[str, str]:
        env: dict[str, str] = {}
        if self.cuda_visible_devices is not None:
            env["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
        return env

    def schedule_deepfloorplan_subprocess(self, command: list[str]) -> None:
        raise NotImplementedError("Launch TF container or subprocess with clean GPU context.")
