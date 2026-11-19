"""
ctypes wrapper around the SecuGen FDx SDK Pro for direct device access.

The wrapper provides minimal helpers to open the reader, capture an ISO 19794
template, and compare templates fully in-process so we can bypass the Windows
Biometric Service/WebAPI.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import ctypes

try:
    from django.conf import settings
except Exception:  # pragma: no cover - standalone usage
    settings = None  # type: ignore

DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
BOOL = ctypes.c_int32
BYTE = ctypes.c_ubyte

SG_DEV_AUTO = 0xFF
SGFDX_ERROR_NONE = 0
SGFDX_ERROR_TIMEOUT = 54

TEMPLATE_FORMAT_ISO19794 = 0x0300
SG_IMPTYPE_LP = 0x00
SG_FINGPOS_UK = 0x00

DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_CAPTURE_QUALITY = 70

DLL_FILENAME = "sgfplib.dll"


class SecuGenError(RuntimeError):
    def __init__(self, code: int, context: str) -> None:
        super().__init__(f"{context} failed (code={code})")
        self.code = code
        self.context = context


@dataclass(slots=True)
class CaptureResult:
    template: bytes
    image_width: int
    image_height: int
    dpi: int
    quality: int

    def to_base64(self) -> str:
        return base64.b64encode(self.template).decode("ascii")


class SGDeviceInfoParam(ctypes.Structure):
    _fields_ = [
        ("DeviceID", DWORD),
        ("DeviceSN", BYTE * 16),
        ("ComPort", DWORD),
        ("ComSpeed", DWORD),
        ("ImageWidth", DWORD),
        ("ImageHeight", DWORD),
        ("Contrast", DWORD),
        ("Brightness", DWORD),
        ("Gain", DWORD),
        ("ImageDPI", DWORD),
        ("FWVersion", DWORD),
    ]


class SGFingerInfo(ctypes.Structure):
    _fields_ = [
        ("FingerNumber", WORD),
        ("ViewNumber", WORD),
        ("ImpressionType", WORD),
        ("ImageQuality", WORD),
    ]


def _dll_directory_from_settings() -> Optional[Path]:
    if settings is None:
        return None
    candidate = getattr(settings, "SECUGEN_DLL_DIR", None)
    return Path(candidate) if candidate else None


class SecuGenDevice:
    def __init__(
        self,
        dll_dir: Optional[Path | str] = None,
        *,
        template_format: int = TEMPLATE_FORMAT_ISO19794,
    ) -> None:
        self.dll_dir = Path(dll_dir or _dll_directory_from_settings() or ".").resolve()
        if not self.dll_dir.exists():
            raise FileNotFoundError(
                f"SecuGen DLL directory '{self.dll_dir}' does not exist."
            )

        self._added_dll_dir = None
        if hasattr(os, "add_dll_directory"):
            self._added_dll_dir = os.add_dll_directory(str(self.dll_dir))

        dll_path = self.dll_dir / DLL_FILENAME
        if not dll_path.exists():
            raise FileNotFoundError(f"Could not find {dll_path}")

        self._dll = ctypes.WinDLL(str(dll_path))
        self._handle = ctypes.c_void_p()
        self._initialized = False
        self._opened = False
        self._template_format = template_format
        self.image_width: Optional[int] = None
        self.image_height: Optional[int] = None
        self.dpi: Optional[int] = None
        self._max_template_size: Optional[int] = None

        self._configure_prototypes()
        self._check(self._dll.SGFPM_Create(ctypes.byref(self._handle)), "SGFPM_Create")

    def _configure_prototypes(self) -> None:
        self._dll.SGFPM_Create.restype = DWORD
        self._dll.SGFPM_Create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]

        self._dll.SGFPM_Terminate.restype = DWORD
        self._dll.SGFPM_Terminate.argtypes = [ctypes.c_void_p]

        self._dll.SGFPM_Init.restype = DWORD
        self._dll.SGFPM_Init.argtypes = [ctypes.c_void_p, DWORD]

        self._dll.SGFPM_InitEx.restype = DWORD
        self._dll.SGFPM_InitEx.argtypes = [ctypes.c_void_p, DWORD, DWORD, DWORD]

        self._dll.SGFPM_OpenDevice.restype = DWORD
        self._dll.SGFPM_OpenDevice.argtypes = [ctypes.c_void_p, DWORD]

        self._dll.SGFPM_CloseDevice.restype = DWORD
        self._dll.SGFPM_CloseDevice.argtypes = [ctypes.c_void_p]

        self._dll.SGFPM_GetDeviceInfo.restype = DWORD
        self._dll.SGFPM_GetDeviceInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(SGDeviceInfoParam),
        ]

        self._dll.SGFPM_SetTemplateFormat.restype = DWORD
        self._dll.SGFPM_SetTemplateFormat.argtypes = [ctypes.c_void_p, WORD]

        self._dll.SGFPM_GetMaxTemplateSize.restype = DWORD
        self._dll.SGFPM_GetMaxTemplateSize.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(DWORD),
        ]

        self._dll.SGFPM_GetImageEx.restype = DWORD
        self._dll.SGFPM_GetImageEx.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(BYTE),
            DWORD,
            ctypes.c_void_p,
            DWORD,
        ]

        self._dll.SGFPM_GetImageQuality.restype = DWORD
        self._dll.SGFPM_GetImageQuality.argtypes = [
            ctypes.c_void_p,
            DWORD,
            DWORD,
            ctypes.POINTER(BYTE),
            ctypes.POINTER(DWORD),
        ]

        self._dll.SGFPM_CreateTemplate.restype = DWORD
        self._dll.SGFPM_CreateTemplate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(SGFingerInfo),
            ctypes.POINTER(BYTE),
            ctypes.POINTER(BYTE),
        ]

        self._dll.SGFPM_GetTemplateSize.restype = DWORD
        self._dll.SGFPM_GetTemplateSize.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(BYTE),
            ctypes.POINTER(DWORD),
        ]

        self._dll.SGFPM_MatchTemplate.restype = DWORD
        self._dll.SGFPM_MatchTemplate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(BYTE),
            ctypes.POINTER(BYTE),
            DWORD,
            ctypes.POINTER(BOOL),
        ]

    def _check(self, code: int, context: str) -> None:
        if code != SGFDX_ERROR_NONE:
            raise SecuGenError(code, context)

    def initialize(
        self, *, width: int | None = None, height: int | None = None, dpi: int | None = None
    ) -> None:
        if self._initialized:
            return
        if width and height and dpi:
            self._check(
                self._dll.SGFPM_InitEx(
                    self._handle,
                    DWORD(width),
                    DWORD(height),
                    DWORD(dpi),
                ),
                "SGFPM_InitEx",
            )
            self.image_width = width
            self.image_height = height
            self.dpi = dpi
        else:
            self._check(
                self._dll.SGFPM_Init(self._handle, DWORD(SG_DEV_AUTO)),
                "SGFPM_Init",
            )
        self._initialized = True
        self._check(
            self._dll.SGFPM_SetTemplateFormat(self._handle, WORD(self._template_format)),
            "SGFPM_SetTemplateFormat",
        )

    def open(self) -> None:
        if self._opened:
            return
        self.initialize()
        self._check(
            self._dll.SGFPM_OpenDevice(self._handle, DWORD(0)),
            "SGFPM_OpenDevice",
        )

        info = SGDeviceInfoParam()
        self._check(
            self._dll.SGFPM_GetDeviceInfo(self._handle, ctypes.byref(info)),
            "SGFPM_GetDeviceInfo",
        )
        self.image_width = info.ImageWidth
        self.image_height = info.ImageHeight
        self.dpi = info.ImageDPI
        self._opened = True

    def close(self) -> None:
        if self._opened:
            try:
                self._dll.SGFPM_CloseDevice(self._handle)
            finally:
                self._opened = False
        if self._initialized:
            try:
                self._dll.SGFPM_Terminate(self._handle)
            finally:
                self._initialized = False
        self._max_template_size = None
        if self._added_dll_dir:
            try:
                self._added_dll_dir.close()
            finally:
                self._added_dll_dir = None

    def __enter__(self) -> "SecuGenDevice":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_template_size(self) -> int:
        if self._max_template_size is not None:
            return self._max_template_size
        if not self._initialized:
            self.initialize()
        out_size = DWORD()
        self._check(
            self._dll.SGFPM_GetMaxTemplateSize(self._handle, ctypes.byref(out_size)),
            "SGFPM_GetMaxTemplateSize",
        )
        self._max_template_size = int(out_size.value)
        return self._max_template_size

    def capture_template(
        self,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        capture_quality: int = DEFAULT_CAPTURE_QUALITY,
    ) -> CaptureResult:
        if not self._opened:
            self.open()

        if not self.image_width or not self.image_height:
            raise RuntimeError("Device information unavailable after open().")

        image_size = int(self.image_width * self.image_height)
        image_buffer = (BYTE * image_size)()

        self._check(
            self._dll.SGFPM_GetImageEx(
                self._handle,
                image_buffer,
                DWORD(timeout_ms),
                None,
                DWORD(capture_quality),
            ),
            "SGFPM_GetImageEx",
        )

        quality = DWORD()
        self._check(
            self._dll.SGFPM_GetImageQuality(
                self._handle,
                DWORD(self.image_width),
                DWORD(self.image_height),
                image_buffer,
                ctypes.byref(quality),
            ),
            "SGFPM_GetImageQuality",
        )

        template_capacity = self._ensure_template_size()
        template_buffer = (BYTE * template_capacity)()

        finger_info = SGFingerInfo(
            WORD(SG_FINGPOS_UK),
            WORD(1),
            WORD(SG_IMPTYPE_LP),
            WORD(min(quality.value, 100)),
        )

        self._check(
            self._dll.SGFPM_CreateTemplate(
                self._handle,
                ctypes.byref(finger_info),
                image_buffer,
                template_buffer,
            ),
            "SGFPM_CreateTemplate",
        )

        actual_size = DWORD()
        self._check(
            self._dll.SGFPM_GetTemplateSize(
                self._handle,
                template_buffer,
                ctypes.byref(actual_size),
            ),
            "SGFPM_GetTemplateSize",
        )

        template_bytes = bytes(template_buffer[: actual_size.value])
        return CaptureResult(
            template=template_bytes,
            image_width=int(self.image_width),
            image_height=int(self.image_height),
            dpi=int(self.dpi or 500),
            quality=int(min(quality.value, 100)),
        )

    def match_templates(
        self,
        probe_template: bytes,
        reference_template: bytes,
        *,
        security_level: int = 5,
        width: int | None = None,
        height: int | None = None,
        dpi: int | None = None,
    ) -> bool:
        if not probe_template or not reference_template:
            raise ValueError("Templates must be non-empty.")

        self.initialize(width=width, height=height, dpi=dpi)

        probe_buf = (BYTE * len(probe_template))(*probe_template)
        ref_buf = (BYTE * len(reference_template))(*reference_template)
        matched = BOOL()
        self._check(
            self._dll.SGFPM_MatchTemplate(
                self._handle,
                probe_buf,
                ref_buf,
                DWORD(security_level),
                ctypes.byref(matched),
            ),
            "SGFPM_MatchTemplate",
        )
        return bool(matched.value)

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass


