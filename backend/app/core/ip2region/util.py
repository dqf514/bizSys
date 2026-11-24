# Copyright 2022 The Ip2Region Authors. All rights reserved.
# Use of this source code is governed by a Apache2.0-style
# license that can be found in the LICENSE file.
#
# 上游来源：https://github.com/lionsoul2014/ip2region/tree/master/binding/python/ip2region
# 本文件为上游纯 Python 绑定的**移植**（仅做 Python 3.13 语法适配，算法未改）。

import ipaddress
import os
from collections.abc import Callable
from typing import BinaryIO

# global constants
XdbStructure20 = 2
XdbStructure30 = 3
XdbIPv4Id = 4
XdbIPv6Id = 6

HeaderInfoLength = 256
VectorIndexRows = 256
VectorIndexCols = 256
VectorIndexSize = 8
# cache of VectorIndexCols × VectorIndexRows × VectorIndexSize
VectorIndexLength = 524288


class Header:
    def __init__(self, buff: bytes) -> None:
        self.version = le_get_uint16(buff, 0)
        self.indexPolicy = le_get_uint16(buff, 2)
        self.createdAt = le_get_uint32(buff, 4)
        self.startIndexPtr = le_get_uint32(buff, 8)
        self.endIndexPtr = le_get_uint32(buff, 12)

        # since IPv6 supporting
        self.ipVersion = le_get_uint16(buff, 16)
        self.runtimePtrBytes = le_get_uint16(buff, 18)

        # keep the raw data
        self.buff = buff

    def __str__(self) -> str:
        return (
            "{"
            f'"version": {self.version}, '
            f'"indexPolicy": {self.indexPolicy}, '
            f'"createdAt": {self.createdAt}, '
            f'"startIndexPtr": {self.startIndexPtr}, '
            f'"endIndexPtr": {self.endIndexPtr}, '
            f'"ipVersion": {self.ipVersion}, '
            f'"runtimePtrBytes": {self.runtimePtrBytes}'
            "}"
        )


# ---
# ip parse and convert functions


def parse_ip(ip_string: str) -> bytes:
    try:
        return ipaddress.ip_address(ip_string).packed
    except ValueError:
        raise ValueError(f"invalid ip address `{ip_string}`") from None


def ip_to_string(ip_bytes: bytes) -> str:
    if isinstance(ip_bytes, bytes):
        return str(ipaddress.ip_address(ip_bytes))
    raise ValueError(f"invalid bytes ip `{ip_bytes}`")


def ip_compare(ip1: bytes, ip2: bytes) -> int:
    if ip1 > ip2:
        return 1
    if ip1 < ip2:
        return -1
    return 0


def ip_sub_compare(ip1: bytes, buff: bytes, offset: int) -> int:
    ip2 = buff[offset : offset + len(ip1)]
    if ip1 > ip2:
        return 1
    if ip1 < ip2:
        return -1
    return 0


# ---
# ip version class and functions


class Version:
    def __init__(
        self,
        id: int,
        name: str,
        byte_num: int,
        index_size: int,
        ip_compare: Callable[[bytes, bytes, int], int],
    ) -> None:
        self.id = id
        self.name = name
        self.byte_num = byte_num
        self.index_size = index_size
        self._ip_compare = ip_compare

    def ip_compare(self, ip1: bytes, ip2: bytes) -> int:
        return self._ip_compare(ip1, ip2, 0)

    def ip_sub_compare(self, ip1: bytes, buff: bytes, offset: int) -> int:
        return self._ip_compare(ip1, buff, offset)


def _v4_sub_compare(ip1: bytes, buff: bytes, offset: int) -> int:
    # ip1: Big endian byte order parsed from input
    # ip2: Little endian byte order read from xdb index.
    # @Note: to compatible with the old Litten endian index encode implementation.
    j = offset + len(ip1) - 1
    for i in range(len(ip1)):
        i1 = ip1[i]
        i2 = buff[j]
        if i1 < i2:
            return -1
        if i1 > i2:
            return 1
        # increase the j
        j = j - 1
    return 0


# ---
# IPv4 and IPv6 version constants
# 14 = 4 + 4 + 2 + 4
IPv4 = Version(XdbIPv4Id, "IPv4", 4, 14, _v4_sub_compare)
# 38 = 16 + 16 + 2 + 4
IPv6 = Version(XdbIPv6Id, "IPv6", 16, 38, ip_sub_compare)


def version_from_name(name: str) -> Version | None:
    u_name = name.upper()
    if u_name in ("IPV4", "V4"):
        return IPv4
    if u_name in ("IPV6", "V6"):
        return IPv6
    return None


def version_from_header(header: Header) -> Version | None:
    # old xdb 2.0 with IPv4 supports ONLY
    if header.version < XdbStructure30:
        return IPv4

    # xdb 3.0 or later version
    ip_version = header.ipVersion
    if ip_version == XdbIPv4Id:
        return IPv4
    if ip_version == XdbIPv6Id:
        return IPv6
    return None


# ---
# buffer decode functions


def le_get_uint32(buff: bytes, offset: int) -> int:
    """
    decode an unsigned 4-bytes int from a buffer started from offset
    with little byte endian
    """
    return (
        ((buff[offset]) & 0x000000FF)
        | ((buff[offset + 1] << 8) & 0x0000FF00)
        | ((buff[offset + 2] << 16) & 0x00FF0000)
        | ((buff[offset + 3] << 24) & 0xFF000000)
    )


def le_get_uint16(buff: bytes, offset: int) -> int:
    """
    decode an unsigned 2-bytes short from a buffer started from offset
    with little byte endian
    """
    return ((buff[offset]) & 0x000000FF) | ((buff[offset + 1] << 8) & 0x0000FF00)


# ---
# xdb buffer load functions


def load_header(handle: BinaryIO) -> Header:
    """
    load xdb header from a specified file handle
    """
    handle.seek(0)
    return Header(handle.read(HeaderInfoLength))


def load_vector_index(handle: BinaryIO) -> bytes:
    """
    load xdb vector index from a specified file handle
    """
    handle.seek(HeaderInfoLength)
    return handle.read(VectorIndexLength)


def load_content(handle: BinaryIO) -> bytes:
    """
    load the whole xdb content from a specified file handle
    """
    handle.seek(0)
    return handle.read()


def verify(handle: BinaryIO) -> None:
    """
    Verify if the current Searcher could be used to search the specified xdb file.
    Why do we need this check ?
    The future features of the xdb impl may cause the current searcher not able to work properly.

    @Note: You Just need to check this ONCE when the service starts.
    """
    header = load_header(handle)

    # get the runtime ptr bytes
    if header.version == XdbStructure20:
        runtime_ptr_bytes = 4
    elif header.version == XdbStructure30:
        runtime_ptr_bytes = header.runtimePtrBytes
    else:
        # Higher versions of the structure are usually incompatible.
        raise ValueError(f"invalid structure version {header.version}")

    # 1, confirm the xdb file size
    # to ensure that the maximum file pointer does not overflow
    max_file_ptr = (1 << (runtime_ptr_bytes * 8)) - 1
    file_bytes = os.stat(handle.fileno()).st_size
    if file_bytes > max_file_ptr:
        raise Exception(f"xdb file exceeds the maximum supported bytes: {max_file_ptr}")
