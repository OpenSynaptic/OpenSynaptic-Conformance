from __future__ import annotations

import ctypes
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any

from shared_runtime import WORKSPACE_ROOT, parse_frame_bytes, truncate_text


OPENSYNAPTIC_ROOT = WORKSPACE_ROOT / "OpenSynaptic"
TX_ROOT = WORKSPACE_ROOT / "OSynaptic-TX"
RX_ROOT = WORKSPACE_ROOT / "OSynaptic-RX"
FX_ROOT = WORKSPACE_ROOT / "OSynaptic-FX"
BUILD_ROOT = Path(__file__).resolve().parent / ".build"


def _shared_suffix() -> str:
    if os.name == "nt":
        return ".dll"
    if sys.platform == "darwin":
        return ".dylib"
    return ".so"


def _compiler_candidates() -> list[str]:
    candidates = []
    for name in ("gcc", "clang", "cc"):
        path = shutil.which(name)
        if path:
            candidates.append(path)
    cl_path = shutil.which("cl")
    if cl_path:
        candidates.append(cl_path)
    return candidates


def _run_build(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "native build failed\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{truncate_text(completed.stdout)}\n"
            f"stderr:\n{truncate_text(completed.stderr)}"
        )


def ensure_shared_library(
    build_key: str,
    repo_root: Path,
    include_dir: Path,
    source_names: list[str],
    c_standard: str,
) -> Path:
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    build_dir = BUILD_ROOT / build_key
    build_dir.mkdir(parents=True, exist_ok=True)
    output_path = build_dir / f"{build_key}{_shared_suffix()}"
    source_paths = [repo_root / "src" / name for name in source_names]

    if output_path.exists():
        newest_source = max(path.stat().st_mtime for path in source_paths)
        if output_path.stat().st_mtime >= newest_source:
            return output_path

    compilers = _compiler_candidates()
    if not compilers:
        raise RuntimeError("no supported C compiler found (expected gcc, clang, cc, or cl)")

    compiler = compilers[0]
    if Path(compiler).name.lower() == "cl.exe":
        command = [
            compiler,
            "/LD",
            "/O2",
            f"/I{include_dir}",
            *[str(path) for path in source_paths],
            f"/Fe:{output_path}",
            f"/std:{'c11' if c_standard == 'c11' else 'c17' if c_standard == 'c17' else 'c11'}",
        ]
        _run_build(command, repo_root)
    else:
        command = [
            compiler,
            "-shared",
            "-O2",
            f"-std={c_standard}",
            "-I",
            str(include_dir),
            *[str(path) for path in source_paths],
            "-o",
            str(output_path),
        ]
        _run_build(command, repo_root)

    if not output_path.exists():
        raise RuntimeError(f"expected shared library was not produced: {output_path}")
    return output_path


def _c_buffer_to_str(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


class TxBackend:
    SOURCE_NAMES = [
        "ostx_b62.c",
        "ostx_crc.c",
        "ostx_packet.c",
        "ostx_sensor.c",
        "ostx_static.c",
        "ostx_stream.c",
    ]

    def __init__(self) -> None:
        library_path = ensure_shared_library(
            "osynaptic_tx",
            TX_ROOT,
            TX_ROOT / "include",
            self.SOURCE_NAMES,
            "c99",
        )
        self.lib = ctypes.CDLL(str(library_path))
        self._configure()

    def _configure(self) -> None:
        self.lib.ostx_b62_encode.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        self.lib.ostx_b62_encode.restype = ctypes.c_int
        self.lib.ostx_crc8.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.ostx_crc8.restype = ctypes.c_uint8
        self.lib.ostx_crc16.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.ostx_crc16.restype = ctypes.c_uint16
        self.lib.ostx_packet_build.argtypes = [
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint32,
            ctypes.c_uint8,
            ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        self.lib.ostx_packet_build.restype = ctypes.c_size_t
        self.lib.ostx_sensor_pack.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint8,
            ctypes.c_uint64,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        self.lib.ostx_sensor_pack.restype = ctypes.c_size_t

    def _as_array(self, data: bytes) -> Any:
        return (ctypes.c_uint8 * len(data)).from_buffer_copy(data)

    def base62_encode(self, value: int) -> str:
        buffer = ctypes.create_string_buffer(32)
        rc = self.lib.ostx_b62_encode(int(value), buffer, len(buffer))
        if rc <= 0:
            raise RuntimeError(f"ostx_b62_encode failed for value {value}")
        return buffer.value.decode("utf-8")

    def crc8(self, data: bytes) -> int:
        return int(self.lib.ostx_crc8(self._as_array(data), len(data)))

    def crc16(self, data: bytes) -> int:
        return int(self.lib.ostx_crc16(self._as_array(data), len(data)))

    def packet_build(self, cmd: int, route: int, aid: int, tid: int, timestamp: int, body: bytes) -> bytes:
        payload = self._as_array(body) if body else None
        output = (ctypes.c_uint8 * 512)()
        size = int(
            self.lib.ostx_packet_build(
                cmd,
                route,
                aid,
                tid,
                timestamp,
                payload,
                len(body),
                output,
                len(output),
            )
        )
        if size <= 0:
            raise RuntimeError("ostx_packet_build failed")
        return bytes(output[:size])

    def sensor_pack(self, aid: int, tid: int, timestamp: int, sensor_id: str, unit: str, scaled: int) -> bytes:
        output = (ctypes.c_uint8 * 512)()
        size = int(
            self.lib.ostx_sensor_pack(
                aid,
                tid,
                timestamp,
                sensor_id.encode("utf-8"),
                unit.encode("utf-8"),
                int(scaled),
                output,
                len(output),
            )
        )
        if size <= 0:
            raise RuntimeError("ostx_sensor_pack failed")
        return bytes(output[:size])


class RxPacketMeta(ctypes.Structure):
    _fields_ = [
        ("cmd", ctypes.c_uint8),
        ("route_count", ctypes.c_uint8),
        ("aid", ctypes.c_uint32),
        ("tid", ctypes.c_uint8),
        ("ts_sec", ctypes.c_uint32),
        ("body_off", ctypes.c_int),
        ("body_len", ctypes.c_int),
        ("crc8_ok", ctypes.c_int),
        ("crc16_ok", ctypes.c_int),
    ]


class RxSensorField(ctypes.Structure):
    _fields_ = [
        ("sensor_id", ctypes.c_char * 32),
        ("unit", ctypes.c_char * 16),
        ("scaled", ctypes.c_int32),
    ]


class RxBackend:
    SOURCE_NAMES = [
        "osrx_b62.c",
        "osrx_crc.c",
        "osrx_packet.c",
        "osrx_parser.c",
        "osrx_sensor.c",
    ]

    def __init__(self) -> None:
        library_path = ensure_shared_library(
            "osynaptic_rx",
            RX_ROOT,
            RX_ROOT / "include",
            self.SOURCE_NAMES,
            "c99",
        )
        self.lib = ctypes.CDLL(str(library_path))
        self._configure()

    def _configure(self) -> None:
        self.lib.osrx_b62_decode.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32)]
        self.lib.osrx_b62_decode.restype = ctypes.c_int
        self.lib.osrx_crc8.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.osrx_crc8.restype = ctypes.c_uint8
        self.lib.osrx_crc16.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.osrx_crc16.restype = ctypes.c_uint16
        self.lib.osrx_packet_decode.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(RxPacketMeta),
        ]
        self.lib.osrx_packet_decode.restype = ctypes.c_int
        self.lib.osrx_sensor_recv.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_int,
            ctypes.POINTER(RxPacketMeta),
            ctypes.POINTER(RxSensorField),
        ]
        self.lib.osrx_sensor_recv.restype = ctypes.c_int

    def _as_array(self, data: bytes) -> Any:
        return (ctypes.c_uint8 * len(data)).from_buffer_copy(data)

    def base62_decode(self, text: str) -> int:
        output = ctypes.c_uint32(0)
        rc = self.lib.osrx_b62_decode(text.encode("utf-8"), ctypes.byref(output))
        if rc != 1:
            raise RuntimeError(f"osrx_b62_decode failed for {text!r}")
        return int(output.value)

    def crc8(self, data: bytes) -> int:
        return int(self.lib.osrx_crc8(self._as_array(data), len(data)))

    def crc16(self, data: bytes) -> int:
        return int(self.lib.osrx_crc16(self._as_array(data), len(data)))

    def packet_decode(self, packet: bytes) -> dict[str, Any]:
        meta = RxPacketMeta()
        rc = self.lib.osrx_packet_decode(self._as_array(packet), len(packet), ctypes.byref(meta))
        return {
            "rc": int(rc),
            "cmd": int(meta.cmd),
            "route_count": int(meta.route_count),
            "source_aid": int(meta.aid),
            "tid": int(meta.tid),
            "timestamp_raw": int(meta.ts_sec),
            "body_offset": int(meta.body_off),
            "body_len": int(meta.body_len),
            "crc8_ok": bool(meta.crc8_ok),
            "crc16_ok": bool(meta.crc16_ok),
        }

    def sensor_recv(self, packet: bytes) -> dict[str, Any]:
        meta = RxPacketMeta()
        field = RxSensorField()
        rc = self.lib.osrx_sensor_recv(
            self._as_array(packet),
            len(packet),
            ctypes.byref(meta),
            ctypes.byref(field),
        )
        return {
            "rc": int(rc),
            "sensorId": _c_buffer_to_str(bytes(field.sensor_id)),
            "unit": _c_buffer_to_str(bytes(field.unit)),
            "scaled": int(field.scaled),
            "cmd": int(meta.cmd),
            "source_aid": int(meta.aid),
            "tid": int(meta.tid),
            "timestamp_raw": int(meta.ts_sec),
            "body_len": int(meta.body_len),
            "crc8_ok": bool(meta.crc8_ok),
            "crc16_ok": bool(meta.crc16_ok),
        }


class FxPacketMeta(ctypes.Structure):
    _fields_ = [
        ("cmd", ctypes.c_uint8),
        ("route_count", ctypes.c_uint8),
        ("source_aid", ctypes.c_uint32),
        ("tid", ctypes.c_uint8),
        ("timestamp_raw", ctypes.c_uint64),
        ("body_offset", ctypes.c_size_t),
        ("body_len", ctypes.c_size_t),
        ("crc8_ok", ctypes.c_int),
        ("crc16_ok", ctypes.c_int),
    ]


class FxFusionEntry(ctypes.Structure):
    _fields_ = [
        ("source_aid", ctypes.c_uint32),
        ("tid", ctypes.c_uint8),
        ("sensor_count", ctypes.c_uint8),
        ("val_count", ctypes.c_uint8),
        ("used", ctypes.c_uint8),
        ("sig_base", ctypes.c_char * 64),
        ("tag_names", (ctypes.c_char * 12) * 4),
        ("tag_name_lens", ctypes.c_uint8 * 4),
        ("last_vals", ((ctypes.c_char * 16) * 8)),
        ("last_val_lens", ctypes.c_uint8 * 8),
    ]


class FxFusionState(ctypes.Structure):
    _fields_ = [("entries", FxFusionEntry * 32)]


class FxCoreSensorInput(ctypes.Structure):
    _fields_ = [
        ("sensor_id", ctypes.c_char_p),
        ("sensor_state", ctypes.c_char_p),
        ("value", ctypes.c_double),
        ("unit", ctypes.c_char_p),
        ("geohash_id", ctypes.c_char_p),
        ("supplementary_message", ctypes.c_char_p),
        ("resource_url", ctypes.c_char_p),
    ]


class FxCoreSensorOutput(ctypes.Structure):
    _fields_ = [
        ("sensor_id", ctypes.c_char * 32),
        ("sensor_state", ctypes.c_char * 32),
        ("value", ctypes.c_double),
        ("unit", ctypes.c_char * 16),
        ("geohash_id", ctypes.c_char * 32),
        ("supplementary_message", ctypes.c_char * 128),
        ("resource_url", ctypes.c_char * 128),
    ]


class FxSecureSession(ctypes.Structure):
    _fields_ = [
        ("aid", ctypes.c_uint32),
        ("last_seen", ctypes.c_uint64),
        ("last_data_timestamp", ctypes.c_uint64),
        ("first_plaintext_ts", ctypes.c_uint64),
        ("pending_timestamp", ctypes.c_uint64),
        ("key", ctypes.c_uint8 * 32),
        ("pending_key", ctypes.c_uint8 * 32),
        ("key_set", ctypes.c_int),
        ("pending_key_set", ctypes.c_int),
        ("dict_ready", ctypes.c_int),
        ("decrypt_confirmed", ctypes.c_int),
        ("state", ctypes.c_int),
        ("used", ctypes.c_int),
    ]


class FxSecureStore(ctypes.Structure):
    _fields_ = [
        ("sessions", FxSecureSession * 64),
        ("expire_seconds", ctypes.c_uint64),
    ]


class FxIdAllocatorEntry(ctypes.Structure):
    _fields_ = [
        ("aid", ctypes.c_uint32),
        ("leased_until", ctypes.c_uint64),
        ("last_seen", ctypes.c_uint64),
        ("in_use", ctypes.c_int),
    ]


class FxIdAllocator(ctypes.Structure):
    _fields_ = [
        ("start_id", ctypes.c_uint32),
        ("end_id", ctypes.c_uint32),
        ("default_lease_seconds", ctypes.c_uint64),
        ("min_lease_seconds", ctypes.c_uint64),
        ("max_lease_seconds", ctypes.c_uint64),
        ("rate_window_seconds", ctypes.c_uint64),
        ("high_rate_threshold_per_hour", ctypes.c_double),
        ("high_rate_min_factor", ctypes.c_double),
        ("pressure_high_watermark", ctypes.c_double),
        ("pressure_min_factor", ctypes.c_double),
        ("touch_extend_factor", ctypes.c_double),
        ("adaptive_enabled", ctypes.c_int),
        ("recent_window_start", ctypes.c_uint64),
        ("recent_alloc_count", ctypes.c_uint32),
        ("entries", FxIdAllocatorEntry * 1024),
    ]


class FxDispatchResult(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_int),
        ("cmd", ctypes.c_uint8),
        ("base_cmd", ctypes.c_uint8),
        ("source_aid", ctypes.c_uint32),
        ("ok", ctypes.c_int),
        ("reject", ctypes.c_int),
        ("has_response", ctypes.c_int),
        ("response", ctypes.c_uint8 * 128),
        ("response_len", ctypes.c_size_t),
    ]


class FxBackend:
    SOURCE_NAMES = [
        "osfx_solidity.c",
        "osfx_fusion_packet.c",
        "osfx_fusion_state.c",
        "osfx_standardization.c",
        "osfx_template_grammar.c",
        "osfx_secure_session.c",
        "osfx_id_allocator.c",
        "osfx_handshake_cmd.c",
        "osfx_handshake_dispatch.c",
        "osfx_payload_crypto.c",
        "osfx_protocol_matrix.c",
        "osfx_transporter_runtime.c",
        "osfx_service_runtime.c",
        "osfx_platform_runtime.c",
        "osfx_plugin_transport.c",
        "osfx_plugin_test.c",
        "osfx_plugin_port_forwarder.c",
        "osfx_cli_lite.c",
        "osfx_glue.c",
        "osfx_core_facade.c",
        "osfx_library_catalog.c",
        "osfx_storage.c",
    ]

    DISPATCH_KIND_ERROR = 0
    DISPATCH_KIND_DATA = 1
    DISPATCH_KIND_CTRL = 2
    DISPATCH_KIND_UNKNOWN = 3
    REJECT_MALFORMED = 1
    REJECT_CRC = 2
    REJECT_REPLAY = 3
    REJECT_OUT_OF_ORDER = 4
    REJECT_NO_SESSION = 5
    REJECT_UNSUPPORTED = 6
    TS_ACCEPT = 0
    TS_REPLAY = 1
    TS_OUT_OF_ORDER = 2

    def __init__(self) -> None:
        library_path = ensure_shared_library(
            "osynaptic_fx",
            FX_ROOT,
            FX_ROOT / "include",
            self.SOURCE_NAMES,
            "c99",
        )
        self.lib = ctypes.CDLL(str(library_path))
        self._configure()

    def _configure(self) -> None:
        self.lib.osfx_b62_encode_i64.argtypes = [ctypes.c_longlong, ctypes.c_char_p, ctypes.c_size_t]
        self.lib.osfx_b62_encode_i64.restype = ctypes.c_int
        self.lib.osfx_b62_decode_i64.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_longlong)]
        self.lib.osfx_b62_decode_i64.restype = ctypes.c_int
        self.lib.osfx_crc8.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.osfx_crc8.restype = ctypes.c_uint8
        self.lib.osfx_crc16_ccitt.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.osfx_crc16_ccitt.restype = ctypes.c_uint16
        self.lib.osfx_packet_decode_meta.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(FxPacketMeta),
        ]
        self.lib.osfx_packet_decode_meta.restype = ctypes.c_int
        self.lib.osfx_fusion_state_init.argtypes = [ctypes.POINTER(FxFusionState)]
        self.lib.osfx_core_encode_sensor_packet_auto.argtypes = [
            ctypes.POINTER(FxFusionState),
            ctypes.c_uint32,
            ctypes.c_uint8,
            ctypes.c_uint64,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        self.lib.osfx_core_encode_sensor_packet_auto.restype = ctypes.c_size_t
        self.lib.osfx_core_encode_multi_sensor_packet_auto.argtypes = [
            ctypes.POINTER(FxFusionState),
            ctypes.c_uint32,
            ctypes.c_uint8,
            ctypes.c_uint64,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(FxCoreSensorInput),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint8),
        ]
        self.lib.osfx_core_encode_multi_sensor_packet_auto.restype = ctypes.c_int
        self.lib.osfx_core_decode_multi_sensor_packet_auto.argtypes = [
            ctypes.POINTER(FxFusionState),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(FxCoreSensorOutput),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(FxPacketMeta),
        ]
        self.lib.osfx_core_decode_multi_sensor_packet_auto.restype = ctypes.c_int
        self.lib.osfx_core_decode_sensor_packet_auto.argtypes = [
            ctypes.POINTER(FxFusionState),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(FxPacketMeta),
        ]
        self.lib.osfx_core_decode_sensor_packet_auto.restype = ctypes.c_int
        self.lib.osfx_secure_store_init.argtypes = [ctypes.POINTER(FxSecureStore), ctypes.c_uint64]
        self.lib.osfx_secure_store_init.restype = None
        self.lib.osfx_secure_note_plaintext_sent.argtypes = [ctypes.POINTER(FxSecureStore), ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64]
        self.lib.osfx_secure_note_plaintext_sent.restype = ctypes.c_int
        self.lib.osfx_secure_confirm_dict.argtypes = [
            ctypes.POINTER(FxSecureStore),
            ctypes.c_uint32,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        self.lib.osfx_secure_confirm_dict.restype = ctypes.c_int
        self.lib.osfx_secure_mark_channel.argtypes = [ctypes.POINTER(FxSecureStore), ctypes.c_uint32, ctypes.c_uint64]
        self.lib.osfx_secure_mark_channel.restype = ctypes.c_int
        self.lib.osfx_secure_should_encrypt.argtypes = [ctypes.POINTER(FxSecureStore), ctypes.c_uint32]
        self.lib.osfx_secure_should_encrypt.restype = ctypes.c_int
        self.lib.osfx_secure_get_key.argtypes = [
            ctypes.POINTER(FxSecureStore),
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint8),
        ]
        self.lib.osfx_secure_get_key.restype = ctypes.c_int
        self.lib.osfx_secure_store_cleanup.argtypes = [ctypes.POINTER(FxSecureStore), ctypes.c_uint64]
        self.lib.osfx_secure_store_cleanup.restype = None
        self.lib.osfx_secure_check_and_update_timestamp.argtypes = [
            ctypes.POINTER(FxSecureStore),
            ctypes.c_uint32,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        self.lib.osfx_secure_check_and_update_timestamp.restype = ctypes.c_int
        self.lib.osfx_id_allocator_init.argtypes = [
            ctypes.POINTER(FxIdAllocator),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint64,
        ]
        self.lib.osfx_id_allocator_init.restype = None
        self.lib.osfx_id_allocate.argtypes = [ctypes.POINTER(FxIdAllocator), ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint32)]
        self.lib.osfx_id_allocate.restype = ctypes.c_int
        self.lib.osfx_id_release.argtypes = [ctypes.POINTER(FxIdAllocator), ctypes.c_uint32]
        self.lib.osfx_id_release.restype = ctypes.c_int
        self.lib.osfx_id_allocator_cleanup_expired.argtypes = [ctypes.POINTER(FxIdAllocator), ctypes.c_uint64]
        self.lib.osfx_id_allocator_cleanup_expired.restype = None
        self.lib.osfx_hs_classify_dispatch.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(FxDispatchResult),
        ]
        self.lib.osfx_hs_classify_dispatch.restype = ctypes.c_int

    def _as_array(self, data: bytes) -> Any:
        return (ctypes.c_uint8 * len(data)).from_buffer_copy(data)

    def new_state(self) -> FxFusionState:
        state = FxFusionState()
        self.lib.osfx_fusion_state_init(ctypes.byref(state))
        return state

    def base62_encode(self, value: int) -> str:
        buffer = ctypes.create_string_buffer(64)
        rc = self.lib.osfx_b62_encode_i64(int(value), buffer, len(buffer))
        if rc <= 0:
            raise RuntimeError(f"osfx_b62_encode_i64 failed for value {value}")
        return buffer.value.decode("utf-8")

    def base62_decode(self, text: str) -> int:
        output = ctypes.c_longlong(0)
        rc = self.lib.osfx_b62_decode_i64(text.encode("utf-8"), ctypes.byref(output))
        if rc != 1:
            raise RuntimeError(f"osfx_b62_decode_i64 failed for {text!r}")
        return int(output.value)

    def crc8(self, data: bytes) -> int:
        return int(self.lib.osfx_crc8(self._as_array(data), len(data)))

    def crc16(self, data: bytes) -> int:
        return int(self.lib.osfx_crc16_ccitt(self._as_array(data), len(data)))

    def packet_decode(self, packet: bytes) -> dict[str, Any]:
        meta = FxPacketMeta()
        rc = self.lib.osfx_packet_decode_meta(self._as_array(packet), len(packet), ctypes.byref(meta))
        return {
            "rc": int(rc),
            "cmd": int(meta.cmd),
            "route_count": int(meta.route_count),
            "source_aid": int(meta.source_aid),
            "tid": int(meta.tid),
            "timestamp_raw": int(meta.timestamp_raw),
            "body_len": int(meta.body_len),
            "crc8_ok": bool(meta.crc8_ok),
            "crc16_ok": bool(meta.crc16_ok),
        }

    def encode_sensor_packet(self, aid: int, tid: int, timestamp: int, sensor_id: str, unit: str, value: float) -> bytes:
        state = self.new_state()
        return self.encode_sensor_packet_with_state(state, aid, tid, timestamp, sensor_id, unit, value)

    def encode_sensor_packet_with_state(
        self,
        state: FxFusionState,
        aid: int,
        tid: int,
        timestamp: int,
        sensor_id: str,
        unit: str,
        value: float,
    ) -> bytes:
        output = (ctypes.c_uint8 * 512)()
        size = int(
            self.lib.osfx_core_encode_sensor_packet_auto(
                ctypes.byref(state),
                aid,
                tid,
                timestamp,
                sensor_id.encode("utf-8"),
                unit.encode("utf-8"),
                float(value),
                output,
                len(output),
            )
        )
        if size <= 0:
            raise RuntimeError("osfx_core_encode_sensor_packet_auto failed")
        return bytes(output[:size])

    def encode_multi_sensor_packet(
        self,
        aid: int,
        tid: int,
        timestamp: int,
        sensors: list[tuple[str, str, float]],
        state: FxFusionState | None = None,
    ) -> bytes:
        active_state = state if state is not None else self.new_state()
        sensor_array = (FxCoreSensorInput * len(sensors))(
            *[
                FxCoreSensorInput(
                    sensor_id.encode("utf-8"),
                    b"OK",
                    float(value),
                    unit.encode("utf-8"),
                    None,
                    None,
                    None,
                )
                for sensor_id, unit, value in sensors
            ]
        )
        output = (ctypes.c_uint8 * 1024)()
        packet_len = ctypes.c_int(0)
        out_cmd = ctypes.c_uint8(0)
        rc = int(
            self.lib.osfx_core_encode_multi_sensor_packet_auto(
                ctypes.byref(active_state),
                aid,
                tid,
                timestamp,
                b"NODE",
                b"ONLINE",
                sensor_array,
                len(sensors),
                output,
                len(output),
                ctypes.byref(packet_len),
                ctypes.byref(out_cmd),
            )
        )
        if rc != 1 or packet_len.value <= 0:
            raise RuntimeError("osfx_core_encode_multi_sensor_packet_auto failed")
        return bytes(output[: packet_len.value])

    def decode_multi_sensor_packet(self, packet: bytes, state: FxFusionState | None = None) -> dict[str, Any]:
        active_state = state if state is not None else self.new_state()
        node_id = ctypes.create_string_buffer(64)
        node_state = ctypes.create_string_buffer(64)
        sensors = (FxCoreSensorOutput * 8)()
        sensor_count = ctypes.c_size_t(0)
        meta = FxPacketMeta()
        rc = int(
            self.lib.osfx_core_decode_multi_sensor_packet_auto(
                ctypes.byref(active_state),
                self._as_array(packet),
                len(packet),
                node_id,
                len(node_id),
                node_state,
                len(node_state),
                sensors,
                len(sensors),
                ctypes.byref(sensor_count),
                ctypes.byref(meta),
            )
        )
        decoded_sensors = []
        for index in range(sensor_count.value):
            item = sensors[index]
            decoded_sensors.append(
                {
                    "sensorId": _c_buffer_to_str(bytes(item.sensor_id)),
                    "state": _c_buffer_to_str(bytes(item.sensor_state)),
                    "value": float(item.value),
                    "unit": _c_buffer_to_str(bytes(item.unit)),
                }
            )
        return {
            "rc": rc,
            "nodeId": node_id.value.decode("utf-8", errors="ignore"),
            "nodeState": node_state.value.decode("utf-8", errors="ignore"),
            "sensors": decoded_sensors,
            "cmd": int(meta.cmd),
            "source_aid": int(meta.source_aid),
            "tid": int(meta.tid),
            "timestamp_raw": int(meta.timestamp_raw),
            "body_len": int(meta.body_len),
            "crc8_ok": bool(meta.crc8_ok),
            "crc16_ok": bool(meta.crc16_ok),
        }

    def decode_sensor_packet(self, packet: bytes, state: FxFusionState | None = None) -> dict[str, Any]:
        active_state = state if state is not None else self.new_state()
        sensor_id = ctypes.create_string_buffer(64)
        unit = ctypes.create_string_buffer(64)
        value = ctypes.c_double(0.0)
        meta = FxPacketMeta()
        rc = self.lib.osfx_core_decode_sensor_packet_auto(
            ctypes.byref(active_state),
            self._as_array(packet),
            len(packet),
            sensor_id,
            len(sensor_id),
            ctypes.byref(value),
            unit,
            len(unit),
            ctypes.byref(meta),
        )
        return {
            "rc": int(rc),
            "sensorId": sensor_id.value.decode("utf-8", errors="ignore"),
            "unit": unit.value.decode("utf-8", errors="ignore"),
            "value": float(value.value),
            "cmd": int(meta.cmd),
            "source_aid": int(meta.source_aid),
            "tid": int(meta.tid),
            "timestamp_raw": int(meta.timestamp_raw),
            "body_len": int(meta.body_len),
            "crc8_ok": bool(meta.crc8_ok),
            "crc16_ok": bool(meta.crc16_ok),
        }

    def classify_dispatch(self, packet: bytes) -> dict[str, Any]:
        result = FxDispatchResult()
        rc = self.lib.osfx_hs_classify_dispatch(None, self._as_array(packet), len(packet), ctypes.byref(result))
        return {
            "rc": int(rc),
            "kind": int(result.kind),
            "cmd": int(result.cmd),
            "base_cmd": int(result.base_cmd),
            "source_aid": int(result.source_aid),
            "ok": bool(result.ok),
            "rejected": int(result.reject) != 0,
            "reject_reason": int(result.reject),
            "has_response": bool(result.has_response),
            "response": bytes(result.response[: result.response_len]),
        }

    def secure_full_handshake(self, aid: int, timestamp: int, dictionary: bytes = b"alpha-dict") -> dict[str, Any]:
        store = FxSecureStore()
        self.lib.osfx_secure_store_init(ctypes.byref(store), 60)
        step_plain = int(self.lib.osfx_secure_note_plaintext_sent(ctypes.byref(store), aid, timestamp, timestamp))
        step_dict = int(self.lib.osfx_secure_confirm_dict(ctypes.byref(store), aid, timestamp, timestamp + 1))
        step_secure = int(self.lib.osfx_secure_mark_channel(ctypes.byref(store), aid, timestamp + 2))
        key_buffer = (ctypes.c_uint8 * 32)()
        key_ok = int(self.lib.osfx_secure_get_key(ctypes.byref(store), aid, key_buffer))
        should_encrypt = bool(self.lib.osfx_secure_should_encrypt(ctypes.byref(store), aid))
        return {
            "store": store,
            "plainOk": bool(step_plain),
            "dictOk": bool(step_dict),
            "secureOk": bool(step_secure),
            "shouldEncrypt": should_encrypt,
            "keyOk": bool(key_ok),
            "key": bytes(key_buffer),
            "keyLen": 32 if key_ok == 1 else 0,
        }

    def secure_timestamp_check(self, aid: int, timestamps: list[int]) -> list[int]:
        store = FxSecureStore()
        self.lib.osfx_secure_store_init(ctypes.byref(store), 60)
        self.lib.osfx_secure_note_plaintext_sent(ctypes.byref(store), aid, timestamps[0] - 1, timestamps[0] - 1)
        results: list[int] = []
        for value in timestamps:
            rc = self.lib.osfx_secure_check_and_update_timestamp(ctypes.byref(store), aid, value, value)
            results.append(int(rc))
        return results

    def secure_isolation(self, aids: list[int], start_ts: int) -> dict[str, Any]:
        store = FxSecureStore()
        self.lib.osfx_secure_store_init(ctypes.byref(store), 60)
        keys: dict[int, bytes] = {}
        states: dict[int, bool] = {}
        for index, aid in enumerate(aids):
            base_ts = start_ts + index * 10
            self.lib.osfx_secure_note_plaintext_sent(ctypes.byref(store), aid, base_ts, base_ts)
            self.lib.osfx_secure_confirm_dict(ctypes.byref(store), aid, base_ts, base_ts + 1)
            self.lib.osfx_secure_mark_channel(ctypes.byref(store), aid, base_ts + 2)
            key_buffer = (ctypes.c_uint8 * 32)()
            key_ok = int(self.lib.osfx_secure_get_key(ctypes.byref(store), aid, key_buffer))
            keys[aid] = bytes(key_buffer) if key_ok == 1 else b""
            states[aid] = bool(self.lib.osfx_secure_should_encrypt(ctypes.byref(store), aid))
        session_count = sum(1 for session in store.sessions if session.used)
        return {"keys": keys, "states": states, "sessionCount": session_count}

    def secure_expiry(self, aid: int, start_ts: int, expire_seconds: int) -> dict[str, Any]:
        store = FxSecureStore()
        self.lib.osfx_secure_store_init(ctypes.byref(store), expire_seconds)
        self.lib.osfx_secure_note_plaintext_sent(ctypes.byref(store), aid, start_ts, start_ts)
        self.lib.osfx_secure_confirm_dict(ctypes.byref(store), aid, start_ts, start_ts + 1)
        self.lib.osfx_secure_mark_channel(ctypes.byref(store), aid, start_ts + 2)
        before = bool(self.lib.osfx_secure_should_encrypt(ctypes.byref(store), aid))
        self.lib.osfx_secure_store_cleanup(ctypes.byref(store), start_ts + expire_seconds + 5)
        after = bool(self.lib.osfx_secure_should_encrypt(ctypes.byref(store), aid))
        return {
            "before": before,
            "after": after,
            "sessionCount": sum(1 for session in store.sessions if session.used),
        }

    def id_allocate_many(self, count: int, start_id: int, end_id: int, lease_seconds: int = 60, start_ts: int = 1_710_000_000) -> list[int]:
        allocator = FxIdAllocator()
        self.lib.osfx_id_allocator_init(ctypes.byref(allocator), start_id, end_id, lease_seconds)
        values: list[int] = []
        for index in range(count):
            aid = ctypes.c_uint32(0)
            rc = int(self.lib.osfx_id_allocate(ctypes.byref(allocator), start_ts + index, ctypes.byref(aid)))
            if rc != 1:
                raise RuntimeError(f"osfx_id_allocate failed at index {index}")
            values.append(int(aid.value))
        return values

    def id_exhaustion(self, start_id: int, end_id: int, lease_seconds: int = 60, start_ts: int = 1_710_000_000) -> dict[str, Any]:
        allocator = FxIdAllocator()
        self.lib.osfx_id_allocator_init(ctypes.byref(allocator), start_id, end_id, lease_seconds)
        capacity = end_id - start_id + 1
        granted: list[int] = []
        for index in range(capacity):
            aid = ctypes.c_uint32(0)
            rc = int(self.lib.osfx_id_allocate(ctypes.byref(allocator), start_ts + index, ctypes.byref(aid)))
            if rc != 1:
                raise RuntimeError("unexpected allocation failure before exhaustion")
            granted.append(int(aid.value))
        extra = ctypes.c_uint32(0)
        extra_rc = int(self.lib.osfx_id_allocate(ctypes.byref(allocator), start_ts + capacity + 1, ctypes.byref(extra)))
        return {
            "granted": granted,
            "extraRc": extra_rc,
        }

    def id_reclaim(self, start_id: int, end_id: int, lease_seconds: int = 2, start_ts: int = 1_710_000_000) -> dict[str, Any]:
        allocator = FxIdAllocator()
        self.lib.osfx_id_allocator_init(ctypes.byref(allocator), start_id, end_id, lease_seconds)
        first = ctypes.c_uint32(0)
        rc = int(self.lib.osfx_id_allocate(ctypes.byref(allocator), start_ts, ctypes.byref(first)))
        if rc != 1:
            raise RuntimeError("initial osfx_id_allocate failed")
        self.lib.osfx_id_allocator_cleanup_expired(ctypes.byref(allocator), start_ts + lease_seconds + 1)
        second = ctypes.c_uint32(0)
        rc = int(self.lib.osfx_id_allocate(ctypes.byref(allocator), start_ts + lease_seconds + 2, ctypes.byref(second)))
        if rc != 1:
            raise RuntimeError("reclaim osfx_id_allocate failed")
        return {"first": int(first.value), "second": int(second.value)}

    def id_concurrent_allocation(
        self,
        start_id: int,
        end_id: int,
        threads: int,
        requests_per_thread: int,
        lease_seconds: int = 60,
    ) -> dict[str, Any]:
        allocator = FxIdAllocator()
        self.lib.osfx_id_allocator_init(ctypes.byref(allocator), start_id, end_id, lease_seconds)
        collected: list[int] = []
        errors: list[str] = []
        lock = threading.Lock()

        def worker(offset: int) -> None:
            local: list[int] = []
            try:
                for index in range(requests_per_thread):
                    aid = ctypes.c_uint32(0)
                    rc = int(self.lib.osfx_id_allocate(ctypes.byref(allocator), 1_710_000_000 + offset * 1000 + index, ctypes.byref(aid)))
                    if rc == 1:
                        local.append(int(aid.value))
            except Exception as exc:
                with lock:
                    errors.append(str(exc))
            with lock:
                collected.extend(local)

        workers = [threading.Thread(target=worker, args=(idx,)) for idx in range(threads)]
        for worker_thread in workers:
            worker_thread.start()
        for worker_thread in workers:
            worker_thread.join()
        return {
            "values": collected,
            "errors": errors,
        }


class CoreBackend:
    CMD_DATA_FULL = 0x3F
    CMD_DATA_DIFF = 0xAA
    CMD_DATA_HEART = 0x7F
    CMD_PING = 0x09
    CMD_PONG = 0x0A
    CMD_ID_REQUEST = 0x10
    CMD_ID_ASSIGN = 0x11

    def __init__(self) -> None:
        self._imported = False

    def _ensure_imported(self) -> None:
        if self._imported:
            return
        sys.path.insert(0, str(OPENSYNAPTIC_ROOT / "src"))
        self.build_native = __import__("opensynaptic.utils.c.build_native", fromlist=["build_all"])
        capture = io.StringIO()
        with redirect_stdout(capture):
            self.build_native.build_all(show_progress=False, idle_timeout=60.0, max_timeout=180.0)
            OpenSynaptic = importlib.import_module("opensynaptic.core.pycore.core").OpenSynaptic
            OSHandshakeManager = importlib.import_module("opensynaptic.core.pycore.handshake").OSHandshakeManager
            Base62Codec = importlib.import_module("opensynaptic.utils.base62.base62").Base62Codec
            IDAllocator = importlib.import_module("opensynaptic.utils.id_allocator").IDAllocator
            security_core = importlib.import_module("opensynaptic.utils.security.security_core")
            crc8 = security_core.crc8
            crc16_ccitt = security_core.crc16_ccitt
            derive_session_key = security_core.derive_session_key

        self.OpenSynaptic = OpenSynaptic
        self.OSHandshakeManager = OSHandshakeManager
        self.Base62Codec = Base62Codec()
        self.IDAllocator = IDAllocator
        self.crc8_fn = crc8
        self.crc16_fn = crc16_ccitt
        self.derive_session_key = derive_session_key
        self._imported = True

    def base62_encode(self, value: int) -> str:
        self._ensure_imported()
        return str(self.Base62Codec.encode(int(value), use_precision=False))

    def base62_decode(self, text: str) -> int:
        self._ensure_imported()
        return int(self.Base62Codec.decode(text, use_precision=False))

    def crc8(self, data: bytes) -> int:
        self._ensure_imported()
        return int(self.crc8_fn(data))

    def crc16(self, data: bytes) -> int:
        self._ensure_imported()
        return int(self.crc16_fn(data))

    @contextmanager
    def node_context(
        self,
        assigned_id: int = 0x01020304,
        payload_switches: dict[str, Any] | None = None,
        security_settings: dict[str, Any] | None = None,
    ):
        self._ensure_imported()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "Config.json"
            config = {
                "device_id": "CONFORMANCE_NODE",
                "assigned_id": assigned_id,
                "payload_switches": {"SensorId": True},
                "OpenSynaptic_Setting": {"default_medium": "UDP"},
                "Client_Core": {"server_host": "127.0.0.1", "server_port": 8080},
                "Server_Core": {"host": "127.0.0.1", "port": 8080, "Start_ID": 1, "End_ID": 0xFFFFFFFE},
                "engine_settings": {
                    "precision": 4,
                    "active_standardization": True,
                    "active_compression": True,
                    "active_collapse": True,
                    "zero_copy_transport": True,
                },
                "RESOURCES": {
                    "registry": "data/device_registry",
                    "root": str(OPENSYNAPTIC_ROOT / "libraries"),
                },
                "security_settings": security_settings or {},
            }
            if payload_switches:
                config["payload_switches"].update(payload_switches)
            config_path.write_text(json.dumps(config), encoding="utf-8")
            capture = io.StringIO()
            with redirect_stdout(capture):
                node = self.OpenSynaptic(str(config_path))
            yield node

    def transmit_sensor(
        self,
        sensor_id: str,
        value: float,
        unit: str,
        assigned_id: int = 0x01020304,
        tid: int | None = None,
        timestamp: int = 1_710_000_000,
        node: Any | None = None,
    ) -> bytes:
        sensors = [[sensor_id, "OK", float(value), unit]]
        if node is not None:
            capture = io.StringIO()
            with redirect_stdout(capture):
                packet, *_ = node.transmit(sensors=sensors, device_id="TEST", device_status="ONLINE", t=timestamp)
            return bytes(packet)
        with self.node_context(assigned_id=assigned_id) as temp_node:
            capture = io.StringIO()
            with redirect_stdout(capture):
                packet, *_ = temp_node.transmit(sensors=sensors, device_id="TEST", device_status="ONLINE", t=timestamp)
            return bytes(packet)

    def transmit_multi(
        self,
        sensors: list[list[Any]],
        assigned_id: int = 0x01020304,
        timestamp: int = 1_710_000_000,
        node: Any | None = None,
    ) -> bytes:
        if node is not None:
            capture = io.StringIO()
            with redirect_stdout(capture):
                packet, *_ = node.transmit(sensors=sensors, device_id="TEST", device_status="ONLINE", t=timestamp)
            return bytes(packet)
        with self.node_context(assigned_id=assigned_id) as temp_node:
            capture = io.StringIO()
            with redirect_stdout(capture):
                packet, *_ = temp_node.transmit(sensors=sensors, device_id="TEST", device_status="ONLINE", t=timestamp)
            return bytes(packet)

    def receive_packet(self, packet: bytes, assigned_id: int = 0x01020304) -> dict[str, Any]:
        with self.node_context(assigned_id=assigned_id) as node:
            capture = io.StringIO()
            with redirect_stdout(capture):
                decoded = node.receive(packet)
            return decoded

    def receive_packet_with_node(self, node: Any, packet: bytes) -> dict[str, Any]:
        capture = io.StringIO()
        with redirect_stdout(capture):
            return node.receive(packet)

    def receive_via_protocol(self, packet: bytes, assigned_id: int = 0x01020304) -> dict[str, Any]:
        with self.node_context(assigned_id=assigned_id) as node:
            capture = io.StringIO()
            with redirect_stdout(capture):
                return node.receive_via_protocol(packet)

    def strategy_sequence(self, values: list[float], unit: str = "Cel") -> list[int]:
        with self.node_context() as node:
            commands: list[int] = []
            for index, value in enumerate(values):
                packet = self.transmit_sensor("T1", value, unit, timestamp=1_710_000_000 + index, node=node)
                commands.append(packet[0])
            return commands

    def handshake_manager(self, expire_seconds: int = 60) -> Any:
        self._ensure_imported()
        return self.OSHandshakeManager(expire_seconds=expire_seconds)

    @contextmanager
    def handshake_manager_context(self, expire_seconds: int = 60):
        self._ensure_imported()
        with tempfile.TemporaryDirectory() as temp_dir:
            secure_store_path = Path(temp_dir) / "secure_sessions.json"
            manager = self.OSHandshakeManager(
                expire_seconds=expire_seconds,
                registry_dir=temp_dir,
                secure_store_path=str(secure_store_path),
            )
            yield manager

    def handshake_full(self, aid: int, timestamp: int, dictionary: bytes = b"alpha-dict") -> dict[str, Any]:
        with self.handshake_manager_context(expire_seconds=60) as manager:
            key = str(aid)
            state0 = dict(manager.secure_sessions.get(key, {})) or {"state": "INIT"}
            state1 = dict(manager.note_local_plaintext_sent(aid, timestamp))
            manager.confirm_secure_dict(aid, timestamp_raw=timestamp + 1)
            state2 = dict(manager.secure_sessions.get(key, {}))
            state3 = dict(manager.mark_secure_channel(aid))
            return {
                "states": [state0.get("state"), state1.get("state"), state2.get("state"), state3.get("state")],
                "dictReady": bool(state3.get("dict_ready")),
                "key": bytes(state3.get("key") or b""),
                "shouldEncrypt": state3.get("state") == "SECURE" and bool(state3.get("decrypt_confirmed")),
            }

    def handshake_isolation(self, aids: list[int], timestamp: int) -> dict[str, Any]:
        with self.handshake_manager_context(expire_seconds=60) as manager:
            keys: dict[int, bytes] = {}
            for index, aid in enumerate(aids):
                base_ts = timestamp + index * 10
                manager.note_local_plaintext_sent(aid, base_ts)
                manager.confirm_secure_dict(aid, timestamp_raw=base_ts + 1)
                manager.mark_secure_channel(aid)
                keys[aid] = bytes(manager.secure_sessions[str(aid)].get("key") or b"")
            return {
                "states": {aid: manager.secure_sessions[str(aid)].get("state") for aid in aids},
                "keys": keys,
            }

    def handshake_expiry(self, aid: int, timestamp: int, expire_seconds: int) -> dict[str, Any]:
        with self.handshake_manager_context(expire_seconds=expire_seconds) as manager:
            manager.note_local_plaintext_sent(aid, timestamp)
            manager.confirm_secure_dict(aid, timestamp_raw=timestamp + 1)
            manager.mark_secure_channel(aid)
            key = str(aid)
            before = manager.secure_sessions[key].get("state") == "SECURE"
            session = manager.secure_sessions.get(key)
            if session is None:
                return {"before": before, "after": False, "existsAfter": False}
            session["last"] = 0
            manager._last_cleanup = 0
            manager._cleanup_expired()
            remaining = manager.secure_sessions.get(key)
            after = bool(remaining and remaining.get("state") == "SECURE")
            return {
                "before": before,
                "after": after,
                "existsAfter": key in manager.secure_sessions,
            }

    def id_allocate_many(self, count: int, start_id: int, end_id: int, base_lease_seconds: int = 60) -> list[int]:
        self._ensure_imported()
        with tempfile.TemporaryDirectory() as temp_dir:
            allocator = self.IDAllocator(
                start_id=start_id,
                end_id=end_id,
                base_dir=temp_dir,
                persist_file="allocator_state.json",
                lease_policy={"base_lease_seconds": base_lease_seconds},
            )
            return [int(allocator.allocate_id()) for _ in range(count)]

    def id_exhaustion(self, start_id: int, end_id: int, base_lease_seconds: int = 60) -> dict[str, Any]:
        self._ensure_imported()
        capacity = end_id - start_id + 1
        with tempfile.TemporaryDirectory() as temp_dir:
            allocator = self.IDAllocator(
                start_id=start_id,
                end_id=end_id,
                base_dir=temp_dir,
                persist_file="allocator_state.json",
                lease_policy={"base_lease_seconds": base_lease_seconds},
            )
            granted = [int(allocator.allocate_id()) for _ in range(capacity)]
            try:
                extra = {"ok": True, "aid": int(allocator.allocate_id())}
            except RuntimeError as exc:
                extra = {"ok": False, "error": str(exc)}
            return {
                "granted": granted,
                "extra": extra,
            }

    def id_reclaim(self, start_id: int, end_id: int, base_lease_seconds: int = 2) -> dict[str, Any]:
        self._ensure_imported()
        with tempfile.TemporaryDirectory() as temp_dir:
            allocator = self.IDAllocator(
                start_id=start_id,
                end_id=end_id,
                base_dir=temp_dir,
                persist_file="allocator_state.json",
                lease_policy={"base_lease_seconds": base_lease_seconds},
            )
            first = int(allocator.allocate_id())
            allocator.release_id(first, immediate=True)
            second = int(allocator.allocate_id())
            return {"first": first, "second": second}

    def id_concurrent_allocation(self, start_id: int, end_id: int, threads: int, requests_per_thread: int) -> dict[str, Any]:
        self._ensure_imported()
        values: list[int] = []
        errors: list[str] = []
        collector_lock = threading.Lock()
        with tempfile.TemporaryDirectory() as temp_dir:
            allocator = self.IDAllocator(
                start_id=start_id,
                end_id=end_id,
                base_dir=temp_dir,
                persist_file="allocator_state.json",
                lease_policy={"base_lease_seconds": 60},
            )

            def worker() -> None:
                local_values: list[int] = []
                try:
                    for _ in range(requests_per_thread):
                        local_values.append(int(allocator.allocate_id()))
                except Exception as exc:
                    with collector_lock:
                        errors.append(str(exc))
                with collector_lock:
                    values.extend(local_values)

            workers = [threading.Thread(target=worker) for _ in range(threads)]
            for worker_thread in workers:
                worker_thread.start()
            for worker_thread in workers:
                worker_thread.join()

        return {
            "values": values,
            "errors": errors,
        }

    def script_run(self, relative_script: str, timeout: int = 120) -> dict[str, Any]:
        self._ensure_imported()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(OPENSYNAPTIC_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, str(OPENSYNAPTIC_ROOT / relative_script)],
            cwd=OPENSYNAPTIC_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def frame_view(self, packet: bytes) -> dict[str, Any]:
        header = parse_frame_bytes(packet)
        if header is None:
            raise RuntimeError("packet is too short to parse")
        return header