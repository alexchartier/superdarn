#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import struct
import sys
import threading
import time
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path
from typing import Any

import numpy as np
import requests
from netCDF4 import Dataset
from urllib3.exceptions import InsecureRequestWarning


LOGIN_URL = "https://jawara.nipr.ac.jp/login"
LOGIN_ACTION_URL = (
    "https://jawara.nipr.ac.jp/_server"
    "?id=src_lib_common_lib_actions_ts--login_action"
    "&name=%2Fhome%2Fjawara%2Fsrc%2Flib%2Fcommon_lib_actions.ts%3Ftsr-directive-use-server%3D"
)
USER_URL = "https://jawara.nipr.ac.jp/user"
RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)")
BOUNDARY_RE = re.compile(r'boundary="?([^";]+)"?', re.IGNORECASE)
MAX_RANGE_HEADER_CHARS = 7500

NC_DIMENSION = 10
NC_VARIABLE = 11
NC_ATTRIBUTE = 12

NC_BYTE = 1
NC_CHAR = 2
NC_SHORT = 3
NC_INT = 4
NC_FLOAT = 5
NC_DOUBLE = 6

NC_TYPE_TO_DTYPE = {
    NC_BYTE: np.dtype("i1"),
    NC_SHORT: np.dtype(">i2"),
    NC_INT: np.dtype(">i4"),
    NC_FLOAT: np.dtype(">f4"),
    NC_DOUBLE: np.dtype(">f8"),
}


@dataclass(frozen=True)
class CaseConfig:
    name: str
    year: int
    stream: int
    target_lat: float
    target_lon: float


@dataclass(frozen=True)
class CDFVariable:
    name: str
    dimids: tuple[int, ...]
    nc_type: int
    vsize: int
    begin: int
    attrs: dict[str, Any]


@dataclass(frozen=True)
class CDFHeader:
    dimensions: tuple[tuple[str, int], ...]
    global_attrs: dict[str, Any]
    variables: dict[str, CDFVariable]


CASES = [
    CaseConfig(name="han_2008", year=2008, stream=1, target_lat=62.32, target_lon=26.61),
    CaseConfig(name="han_2008_mwr", year=2008, stream=1, target_lat=69.26908, target_lon=16.039558),
    CaseConfig(name="fir_2019", year=2019, stream=3, target_lat=-51.8314, target_lon=-58.9793),
    CaseConfig(name="fir_2020", year=2020, stream=3, target_lat=-51.8314, target_lon=-58.9793),
    CaseConfig(name="mcm_2019", year=2019, stream=3, target_lat=-77.88, target_lon=166.73),
]

VAR_MAP = {
    "u": "U",
    "v": "V",
    "z": "Z",
}


def source_url(case: CaseConfig, month: int, var_name: str) -> str:
    year_suffix = case.year % 100
    file_code = f"{VAR_MAP[var_name]}{year_suffix:02d}{month:02d}.nc"
    return (
        f"https://jawara.nipr.ac.jp/api/jawara/p/stream{case.stream}/"
        f"{case.year}{month:02d}/asm/{file_code}"
    )


def log(msg: str) -> None:
    print(msg, flush=True)


def case_output_path(out_dir: Path, case: CaseConfig) -> Path:
    return case_year_dir(out_dir, case) / f"{case.name}_jawara_hourly_uvz_2x2.nc"


def case_year_dir(out_dir: Path, case: CaseConfig) -> Path:
    site = case.name.split("_", 1)[0]
    return out_dir / site / str(case.year)


def case_month_output_path(out_dir: Path, case: CaseConfig, month: int) -> Path:
    return case_year_dir(out_dir, case) / "monthly" / f"{case.name}_{case.year}{month:02d}_jawara_hourly_uvz_2x2.nc"


def parse_months(spec: str) -> list[int]:
    months: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            months.update(range(start, end + 1))
        else:
            months.add(int(token))
    out = sorted(months)
    if not out or any(month < 1 or month > 12 for month in out):
        raise argparse.ArgumentTypeError(f"Invalid month selection: {spec}")
    return out


def login(session: requests.Session, user: str, password: str) -> None:
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    session.get(LOGIN_URL, timeout=60)
    resp = session.post(
        LOGIN_ACTION_URL,
        data={"userid": user, "password": password},
        headers={"Referer": LOGIN_URL},
        allow_redirects=True,
        timeout=60,
    )
    resp.raise_for_status()

    user_page = session.get(USER_URL, timeout=60)
    user_page.raise_for_status()
    text = user_page.text.lower()
    if "approved" not in text or ("alex" not in text and "hello." not in text):
        raise RuntimeError("JAWARA login did not reach an approved user session.")


def fetch_byte_ranges(
    session: requests.Session,
    url: str,
    ranges: list[tuple[int, int]],
) -> list[bytes]:
    if not ranges:
        return []
    last_error: Exception | None = None
    for attempt in range(1, 6):
        resp = None
        try:
            range_value = "bytes=" + ",".join(f"{start}-{end}" for start, end in ranges)
            resp = session.get(url, headers={"Range": range_value}, timeout=(30, 300))
            if resp.status_code == 400 and len(ranges) > 1:
                resp.close()
                split = len(ranges) // 2
                return fetch_byte_ranges(session, url, ranges[:split]) + fetch_byte_ranges(
                    session, url, ranges[split:]
                )
            resp.raise_for_status()
            if resp.status_code != 206:
                raise RuntimeError(f"Expected HTTP 206 for {url}, got {resp.status_code}")

            if len(ranges) == 1:
                return [resp.content]

            content_type = resp.headers.get("Content-Type", "")
            match = BOUNDARY_RE.search(content_type)
            if "multipart/byteranges" not in content_type.lower() or not match:
                raise RuntimeError(f"Expected multipart/byteranges response, got {content_type!r}")

            mime_bytes = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode() + resp.content
            message = BytesParser(policy=email_policy).parsebytes(mime_bytes)
            parts: dict[tuple[int, int], bytes] = {}
            for part in message.iter_parts():
                crange = part["Content-Range"]
                if crange is None:
                    raise RuntimeError("Missing Content-Range in multipart response")
                range_match = RANGE_RE.fullmatch(str(crange).strip())
                if not range_match:
                    raise RuntimeError(f"Malformed Content-Range: {crange}")
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                body = part.get_payload(decode=True)
                expected_size = end - start + 1
                parts[(start, end)] = body[:expected_size]

            missing = [item for item in ranges if item not in parts]
            if missing:
                raise RuntimeError(f"Missing {len(missing)} byte ranges in multipart response")
            return [parts[item] for item in ranges]
        except Exception as exc:
            last_error = exc
            if attempt >= 5:
                raise
            time.sleep(min(2 * attempt, 10))
        finally:
            if resp is not None:
                resp.close()

    raise RuntimeError(f"Unreachable fetch_byte_ranges failure for {url}") from last_error


def fetch_header_prefix(session: requests.Session, url: str) -> bytes:
    last_error: Exception | None = None
    for end in [65535, 262143, 1048575]:
        try:
            return fetch_byte_ranges(session, url, [(0, end)])[0]
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Unable to fetch a usable NetCDF header prefix for {url}") from last_error


class HeaderReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _take(self, count: int) -> bytes:
        end = self.pos + count
        if end > len(self.data):
            raise ValueError("Header prefix is too short for NetCDF header parsing")
        out = self.data[self.pos:end]
        self.pos = end
        return out

    def read_i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def read_u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def read_name(self) -> str:
        count = self.read_u32()
        raw = self._take(count)
        self.pos += (-count) % 4
        return raw.decode("ascii")

    def read_values(self, nc_type: int, count: int) -> Any:
        if nc_type == NC_CHAR:
            raw = self._take(count)
            self.pos += (-count) % 4
            return raw.decode("ascii")

        dtype = NC_TYPE_TO_DTYPE.get(nc_type)
        if dtype is None:
            raise ValueError(f"Unsupported NetCDF type {nc_type}")

        nbytes = count * dtype.itemsize
        raw = self._take(nbytes)
        self.pos += (-nbytes) % 4
        values = np.frombuffer(raw, dtype=dtype)
        native = values.astype(values.dtype.newbyteorder("="), copy=False)
        if count == 1:
            return native[0].item()
        return native.copy()

    def read_attr_list(self) -> dict[str, Any]:
        tag = self.read_i32()
        count = self.read_i32()
        if tag == 0 and count == 0:
            return {}
        if tag != NC_ATTRIBUTE:
            raise ValueError(f"Unexpected attribute tag {tag}")

        attrs: dict[str, Any] = {}
        for _ in range(count):
            name = self.read_name()
            nc_type = self.read_i32()
            nvalues = self.read_u32()
            attrs[name] = self.read_values(nc_type, nvalues)
        return attrs


def parse_cdf1_header(header_bytes: bytes) -> CDFHeader:
    reader = HeaderReader(header_bytes)
    magic = reader._take(4)
    if magic != b"CDF\x01":
        raise ValueError(f"Expected classic NetCDF (CDF1), got {magic!r}")

    _ = reader.read_u32()

    dim_tag = reader.read_i32()
    ndims = reader.read_i32()
    if dim_tag != NC_DIMENSION:
        raise ValueError(f"Unexpected dimension tag {dim_tag}")
    dimensions = tuple((reader.read_name(), reader.read_u32()) for _ in range(ndims))

    global_attrs = reader.read_attr_list()

    var_tag = reader.read_i32()
    nvars = reader.read_i32()
    if var_tag != NC_VARIABLE:
        raise ValueError(f"Unexpected variable tag {var_tag}")

    variables: dict[str, CDFVariable] = {}
    for _ in range(nvars):
        name = reader.read_name()
        dim_count = reader.read_u32()
        dimids = tuple(reader.read_u32() for _ in range(dim_count))
        attrs = reader.read_attr_list()
        nc_type = reader.read_i32()
        vsize = reader.read_u32()
        begin = reader.read_u32()
        variables[name] = CDFVariable(
            name=name,
            dimids=dimids,
            nc_type=nc_type,
            vsize=vsize,
            begin=begin,
            attrs=attrs,
        )

    return CDFHeader(dimensions=dimensions, global_attrs=global_attrs, variables=variables)


def fetch_header(session: requests.Session, url: str) -> CDFHeader:
    prefix = fetch_header_prefix(session, url)
    return parse_cdf1_header(prefix)


def variable_shape(header: CDFHeader, variable: CDFVariable) -> tuple[int, ...]:
    return tuple(header.dimensions[idx][1] for idx in variable.dimids)


def decode_variable_bytes(data: bytes, variable: CDFVariable, shape: tuple[int, ...]) -> np.ndarray:
    if variable.nc_type == NC_CHAR:
        raise ValueError(f"Unexpected character variable {variable.name}")
    dtype = NC_TYPE_TO_DTYPE[variable.nc_type]
    count = int(np.prod(shape, dtype=np.int64))
    raw = data[: count * dtype.itemsize]
    arr = np.frombuffer(raw, dtype=dtype)
    native_dtype = arr.dtype.newbyteorder("=")
    return arr.astype(native_dtype, copy=False).reshape(shape)


def fetch_small_variable(session: requests.Session, url: str, header: CDFHeader, name: str) -> np.ndarray:
    variable = header.variables[name]
    shape = variable_shape(header, variable)
    end = variable.begin + variable.vsize - 1
    data = fetch_byte_ranges(session, url, [(variable.begin, end)])[0]
    return decode_variable_bytes(data, variable, shape)


def clone_session(session: requests.Session) -> requests.Session:
    clone = requests.Session()
    clone.verify = session.verify
    clone.headers.update(session.headers)
    clone.cookies.update(session.cookies)
    return clone


def iter_range_batches(
    ranges: list[tuple[int, int]],
    indices: list[tuple[int, int]],
    max_ranges_per_request: int,
    max_header_chars: int = MAX_RANGE_HEADER_CHARS,
):
    batch_ranges: list[tuple[int, int]] = []
    batch_indices: list[tuple[int, int]] = []
    header_len = len("bytes=")

    for item_range, item_index in zip(ranges, indices):
        token_len = len(f"{item_range[0]}-{item_range[1]}")
        separator_len = 1 if batch_ranges else 0
        would_exceed = header_len + separator_len + token_len > max_header_chars
        if batch_ranges and (len(batch_ranges) >= max_ranges_per_request or would_exceed):
            yield batch_ranges, batch_indices
            batch_ranges = []
            batch_indices = []
            header_len = len("bytes=")
            separator_len = 0

        batch_ranges.append(item_range)
        batch_indices.append(item_index)
        header_len += separator_len + token_len

    if batch_ranges:
        yield batch_ranges, batch_indices


def lat_bbox_indices(lats: np.ndarray, target_lat: float) -> tuple[int, int]:
    if target_lat >= float(lats[0]):
        return 0, 1
    if target_lat <= float(lats[-1]):
        return len(lats) - 2, len(lats) - 1
    upper = int(np.where(lats >= target_lat)[0][-1])
    return upper, upper + 1


def lon_bbox_indices(lons: np.ndarray, target_lon: float) -> tuple[int, int]:
    target_lon = target_lon % 360.0
    if target_lon <= float(lons[0]):
        return 0, 1
    if target_lon >= float(lons[-1]):
        return len(lons) - 2, len(lons) - 1
    lower = int(np.where(lons <= target_lon)[0][-1])
    return lower, lower + 1


def extract_subset_remote(
    session: requests.Session,
    url: str,
    target_lat: float,
    target_lon: float,
    var_name: str,
    expected_box: dict[str, np.ndarray] | None = None,
    max_ranges_per_request: int = 512,
    progress_label: str | None = None,
    workers: int = 4,
) -> dict[str, np.ndarray]:
    header = fetch_header(session, url)
    lats = np.asarray(fetch_small_variable(session, url, header, "latitude"), dtype=np.float32)
    lons = np.asarray(fetch_small_variable(session, url, header, "longitude"), dtype=np.float32)
    levels = np.asarray(fetch_small_variable(session, url, header, "level"), dtype=np.float32)
    times = np.asarray(fetch_small_variable(session, url, header, "time"), dtype=np.int32)
    time_units = str(header.variables["time"].attrs["units"])

    if expected_box is None:
        lat0, lat1 = lat_bbox_indices(lats, target_lat)
        lon0, lon1 = lon_bbox_indices(lons, target_lon)
    else:
        lat_box = expected_box["latitude"]
        lon_box = expected_box["longitude"]
        lat0 = int(np.where(np.isclose(lats, lat_box[0]))[0][0])
        lat1 = int(np.where(np.isclose(lats, lat_box[-1]))[0][0])
        lon0 = int(np.where(np.isclose(lons, lon_box[0]))[0][0])
        lon1 = int(np.where(np.isclose(lons, lon_box[-1]))[0][0])

    variable = header.variables[var_name]
    ntime, nlevel, nlat, nlon = variable_shape(header, variable)
    if lat1 != lat0 + 1 or lon1 != lon0 + 1:
        raise RuntimeError("This extractor expects adjacent 2x2 latitude/longitude bounds.")

    row_span_bytes = 2 * nlon * 4
    subset = np.empty((ntime, nlevel, 2, 2), dtype=np.float32)

    block_ranges: list[tuple[int, int]] = []
    block_indices: list[tuple[int, int]] = []
    for time_index in range(ntime):
        for level_index in range(nlevel):
            start_elem = (((time_index * nlevel) + level_index) * nlat + lat0) * nlon
            start = variable.begin + start_elem * 4
            end = start + row_span_bytes - 1
            block_ranges.append((start, end))
            block_indices.append((time_index, level_index))

    range_batches = list(iter_range_batches(block_ranges, block_indices, max_ranges_per_request))
    total_batches = len(range_batches)
    report_every = max(1, total_batches // 10)

    thread_local = threading.local()
    worker_sessions: list[requests.Session] = []

    def fetch_batch(batch_ranges: list[tuple[int, int]]) -> list[bytes]:
        worker_session = getattr(thread_local, "session", None)
        if worker_session is None:
            worker_session = clone_session(session)
            thread_local.session = worker_session
            worker_sessions.append(worker_session)
        return fetch_byte_ranges(worker_session, url, batch_ranges)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = [executor.submit(fetch_batch, batch_ranges) for batch_ranges, _ in range_batches]
            for batch_index, ((_, batch_indices), future) in enumerate(zip(range_batches, futures), start=1):
                payloads = future.result()
                for (time_index, level_index), payload in zip(batch_indices, payloads):
                    rows = np.frombuffer(payload, dtype=">f4", count=2 * nlon).astype(np.float32).reshape(2, nlon)
                    subset[time_index, level_index, :, :] = rows[:, lon0 : lon1 + 1]
                if progress_label and (
                    batch_index == 1 or batch_index == total_batches or batch_index % report_every == 0
                ):
                    log(f"    {progress_label}: {100.0 * batch_index / total_batches:5.1f}%")
    finally:
        for worker_session in worker_sessions:
            worker_session.close()

    fill_value = variable.attrs.get("_FillValue", variable.attrs.get("missing_value"))
    if fill_value is not None:
        subset[np.isclose(subset, np.float32(fill_value))] = np.nan

    return {
        "time": times,
        "time_units": time_units,
        "level": levels,
        "latitude": lats[lat0 : lat1 + 1],
        "longitude": lons[lon0 : lon1 + 1],
        "data": subset,
        "lat_indices": np.array([lat0, lat1], dtype=np.int32),
        "lon_indices": np.array([lon0, lon1], dtype=np.int32),
    }


def create_output(case: CaseConfig, out_path: Path, month_data: dict[str, dict[str, np.ndarray]]) -> None:
    template = month_data["u"]
    with Dataset(out_path, "w", format="NETCDF4") as out_ds:
        out_ds.createDimension("time", None)
        out_ds.createDimension("level", len(template["level"]))
        out_ds.createDimension("latitude", len(template["latitude"]))
        out_ds.createDimension("longitude", len(template["longitude"]))

        time_var = out_ds.createVariable("time", "i4", ("time",))
        time_var.units = template["time_units"]

        level_var = out_ds.createVariable("level", "f4", ("level",))
        level_var.units = "hPa"
        level_var.long_name = "pressure"
        level_var.positive = "down"
        level_var[:] = template["level"]

        lat_var = out_ds.createVariable("latitude", "f4", ("latitude",))
        lat_var.units = "degrees_north"
        lat_var[:] = template["latitude"]

        lon_var = out_ds.createVariable("longitude", "f4", ("longitude",))
        lon_var.units = "degrees_east"
        lon_var[:] = template["longitude"]

        for var_name, long_name, units in [
            ("u", "u-velocity", "m/s"),
            ("v", "v-velocity", "m/s"),
            ("z", "geopotential height", "m"),
        ]:
            var = out_ds.createVariable(
                var_name,
                "f4",
                ("time", "level", "latitude", "longitude"),
                zlib=True,
                complevel=4,
                fill_value=np.float32(np.nan),
            )
            var.long_name = long_name
            var.units = units

        out_ds.case_name = case.name
        out_ds.source_dataset = "JAWARA assimilation"
        out_ds.source_frequency = "1hour"
        out_ds.source_stream = str(case.stream)
        out_ds.target_latitude = case.target_lat
        out_ds.target_longitude = case.target_lon
        out_ds.source_lat_indices = ",".join(map(str, template["lat_indices"]))
        out_ds.source_lon_indices = ",".join(map(str, template["lon_indices"]))
        out_ds.note = (
            "Subset created from JAWARA hourly assimilation files. "
            "Spatial subset is a 2x2 lat/lon box bracketing the target radar location."
        )


def append_month(
    out_path: Path,
    month_data: dict[str, dict[str, np.ndarray]],
    month: int,
) -> None:
    time_vals = month_data["u"]["time"]
    ntime = len(time_vals)
    with Dataset(out_path, "r+") as out_ds:
        start = len(out_ds.dimensions["time"])
        end = start + ntime

        ref_level = np.asarray(out_ds.variables["level"][:], dtype=np.float32)
        ref_lat = np.asarray(out_ds.variables["latitude"][:], dtype=np.float32)
        ref_lon = np.asarray(out_ds.variables["longitude"][:], dtype=np.float32)
        if not np.allclose(ref_level, month_data["u"]["level"]):
            raise RuntimeError(f"Level mismatch while appending month {month:02d}")
        if not np.allclose(ref_lat, month_data["u"]["latitude"]):
            raise RuntimeError(f"Latitude mismatch while appending month {month:02d}")
        if not np.allclose(ref_lon, month_data["u"]["longitude"]):
            raise RuntimeError(f"Longitude mismatch while appending month {month:02d}")

        out_ds.variables["time"][start:end] = time_vals
        for var_name in ["u", "v", "z"]:
            out_ds.variables[var_name][start:end, :, :, :] = month_data[var_name]["data"]


def load_subset_file(out_path: Path) -> dict[str, dict[str, np.ndarray]]:
    with Dataset(out_path, "r") as ds:
        time = np.asarray(ds.variables["time"][:], dtype=float)
        time_units = str(ds.variables["time"].units)
        level = np.asarray(ds.variables["level"][:], dtype=np.float32)
        latitude = np.asarray(ds.variables["latitude"][:], dtype=np.float32)
        longitude = np.asarray(ds.variables["longitude"][:], dtype=np.float32)
        lat_indices = np.array([int(tok) for tok in str(ds.getncattr("source_lat_indices")).split(",")], dtype=np.int32)
        lon_indices = np.array([int(tok) for tok in str(ds.getncattr("source_lon_indices")).split(",")], dtype=np.int32)

        month_data: dict[str, dict[str, np.ndarray]] = {}
        for var_name in ["u", "v", "z"]:
            data = np.asarray(ds.variables[var_name][:], dtype=float)
            fill_value = ds.variables[var_name].getncattr("_FillValue") if "_FillValue" in ds.variables[var_name].ncattrs() else None
            if fill_value is None and "missing_value" in ds.variables[var_name].ncattrs():
                fill_value = ds.variables[var_name].getncattr("missing_value")
            if fill_value is not None:
                data[np.isclose(data, fill_value)] = np.nan
            month_data[var_name] = {
                "time": time.copy(),
                "time_units": time_units,
                "level": level.copy(),
                "latitude": latitude.copy(),
                "longitude": longitude.copy(),
                "data": data,
                "lat_indices": lat_indices.copy(),
                "lon_indices": lon_indices.copy(),
            }
    return month_data


def write_subset_file(
    out_path: Path,
    case: CaseConfig,
    month_data: dict[str, dict[str, np.ndarray]],
    month: int,
    overwrite: bool = False,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not overwrite:
        return
    tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
    if tmp_out.exists():
        tmp_out.unlink()
    create_output(case, tmp_out, month_data)
    append_month(tmp_out, month_data, month)
    os.replace(tmp_out, out_path)


def process_case(
    session: requests.Session,
    case: CaseConfig,
    months: list[int],
    out_dir: Path,
    max_ranges_per_request: int,
    workers: int,
    overwrite: bool = False,
) -> Path:
    out_path = case_output_path(out_dir, case)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not overwrite:
        log(f"Skipping existing {out_path}")
        return out_path
    tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
    if tmp_out.exists():
        tmp_out.unlink()

    expected_box = None
    created = False

    try:
        for month in months:
            log(f"{case.name}: month {month:02d}")
            month_path = case_month_output_path(out_dir, case, month)
            month_data: dict[str, dict[str, np.ndarray]] = {}
            if month_path.exists() and not overwrite:
                log(f"  using cached {month_path}")
                month_data = load_subset_file(month_path)
            else:
                for var_name in ["u", "v", "z"]:
                    url = source_url(case, month, var_name)
                    log(f"  extracting {Path(url).name}")
                    subset = extract_subset_remote(
                        session,
                        url,
                        target_lat=case.target_lat,
                        target_lon=case.target_lon,
                        var_name=var_name,
                        expected_box=expected_box,
                        max_ranges_per_request=max_ranges_per_request,
                        progress_label=Path(url).name,
                        workers=workers,
                    )
                    month_data[var_name] = subset
                    if expected_box is None:
                        expected_box = {
                            "latitude": subset["latitude"].copy(),
                            "longitude": subset["longitude"].copy(),
                        }
                        log(
                            "  source box "
                            f"lat={subset['latitude'].tolist()} lon={subset['longitude'].tolist()} "
                            f"indices=lat{subset['lat_indices'].tolist()} lon{subset['lon_indices'].tolist()}"
                        )
                write_subset_file(month_path, case, month_data, month, overwrite=overwrite)

            if not created:
                create_output(case, tmp_out, month_data)
                created = True
            append_month(tmp_out, month_data, month)

        tmp_out.rename(out_path)
        return out_path
    except Exception:
        tmp_out.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and extract compact JAWARA site subsets.")
    parser.add_argument(
        "--out-dir",
        default=str(Path("~/data/meteor_winds/jawara").expanduser()),
        help="Output directory for compact annual subset files.",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=[case.name for case in CASES],
        default=[case.name for case in CASES],
        help="Subset case(s) to process.",
    )
    parser.add_argument(
        "--months",
        type=parse_months,
        default=list(range(1, 13)),
        help="Month selection, e.g. 1,2,12 or 1-12.",
    )
    parser.add_argument(
        "--max-ranges-per-request",
        type=int,
        default=512,
        help="Maximum number of byte ranges to request in a single HTTP call.",
    )
    parser.add_argument(
        "--ca-bundle",
        default=os.environ.get("JAWARA_CA_BUNDLE", "/etc/ssl/cert.pem"),
        help="CA bundle to use for HTTPS requests.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=os.environ.get("JAWARA_INSECURE", "").lower() in {"1", "true", "yes"},
        help="Disable TLS certificate verification for this session.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent HTTP workers to use while extracting each file.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite any existing annual subset file instead of skipping it.",
    )
    args = parser.parse_args()

    user = os.environ.get("JAWARA_USER")
    password = os.environ.get("JAWARA_PASS")
    if not user or not password:
        raise SystemExit("Set JAWARA_USER and JAWARA_PASS in the environment before running this script.")

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    if args.insecure:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
        session.verify = False
    elif args.ca_bundle:
        session.verify = args.ca_bundle

    login(session, user, password)
    log("Logged into JAWARA with approved access.")

    selected = [case for case in CASES if case.name in set(args.cases)]
    outputs = []
    try:
        for case in selected:
            outputs.append(
                process_case(
                    session,
                    case,
                    args.months,
                    out_dir,
                    args.max_ranges_per_request,
                    args.workers,
                    overwrite=args.overwrite,
                )
            )
    finally:
        session.close()

    log("Created subset files:")
    for path in outputs:
        log(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
