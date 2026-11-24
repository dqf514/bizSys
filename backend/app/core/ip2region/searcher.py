# Copyright 2022 The Ip2Region Authors. All rights reserved.
# Use of this source code is governed by a Apache2.0-style
# license that can be found in the LICENSE file.
#
# 上游来源：https://github.com/lionsoul2014/ip2region/tree/master/binding/python/ip2region
# 本文件为上游纯 Python 绑定的**移植**（仅做 Python 3.13 语法适配，算法未改）。

from . import util


class Searcher:
    """
    xdb searcher class with Both IPv4 and IPv6 supported.
    three kinds of cache policy: file / vectorIndex / content
    """

    def __init__(
        self,
        version: util.Version,
        db_path: str | None,
        vector_index: bytes | None,
        c_buffer: bytes | None,
    ) -> None:
        self.version = version
        self.__db_path = db_path
        self.__io_count = 0
        if c_buffer is not None:
            self.__handle = None
            self.vector_index: bytes | None = None
            self.c_buffer: bytes | None = c_buffer
        else:
            if db_path is None:
                raise ValueError("db_path is required without a content buffer")
            self.__handle = open(db_path, "rb")
            self.vector_index = vector_index
            self.c_buffer = None

    def get_ip_version(self) -> util.Version:
        return self.version

    def get_io_count(self) -> int:
        return self.__io_count

    def search(self, ip: bytes | str) -> str:
        # check and parse the string ip
        if isinstance(ip, str):
            ip_bytes = util.parse_ip(ip)
        elif isinstance(ip, bytes):
            ip_bytes = ip
        else:
            raise ValueError(f"invalid ip address `{ip}`")

        # ip version check
        if len(ip_bytes) != self.version.byte_num:
            raise ValueError(
                f"invalid ip address `{util.ip_to_string(ip_bytes)}` ({self.version.name} expected)"
            )

        # reset the global io_count
        self.__io_count = 0

        # located the segment index block based on the vector index
        s_ptr, e_ptr, i0, i1 = 0, 0, ip_bytes[0], ip_bytes[1]
        idx = i0 * util.VectorIndexCols * util.VectorIndexSize + i1 * util.VectorIndexSize
        if self.vector_index is not None:
            s_ptr = util.le_get_uint32(self.vector_index, idx)
            e_ptr = util.le_get_uint32(self.vector_index, idx + 4)
        elif self.c_buffer is not None:
            offset = util.HeaderInfoLength + idx
            s_ptr = util.le_get_uint32(self.c_buffer, offset)
            e_ptr = util.le_get_uint32(self.c_buffer, offset + 4)
        else:
            buff = self.read(util.HeaderInfoLength + idx, util.VectorIndexSize)
            s_ptr = util.le_get_uint32(buff, 0)
            e_ptr = util.le_get_uint32(buff, 4)

        # @Note: ptr validate, zero ptr means source data missing
        # so we could just stop here and return an empty string.
        if s_ptr == 0 or e_ptr == 0:
            return ""

        # binary search the segment index block to get the region info
        _bytes, _d_bytes = len(ip_bytes), len(ip_bytes) << 1
        index_size = self.version.index_size
        d_len, d_ptr, low, high = 0, 0, 0, int((e_ptr - s_ptr) / index_size)
        while low <= high:
            mid = (low + high) >> 1
            ptr = int(s_ptr + mid * index_size)

            # read the segment index
            buff = self.read(ptr, index_size)
            if self.version.ip_sub_compare(ip_bytes, buff, 0) < 0:
                high = mid - 1
            elif self.version.ip_sub_compare(ip_bytes, buff, _bytes) > 0:
                low = mid + 1
            else:
                d_len = util.le_get_uint16(buff, _d_bytes)
                d_ptr = util.le_get_uint32(buff, _d_bytes + 2)
                break

        # empty match interception.
        # and this could be a case.
        if d_len == 0:
            return ""

        # read and return the region info
        return self.read(d_ptr, d_len).decode("utf-8")

    def read(self, offset: int, length: int) -> bytes:
        # check the content buffer first
        if self.c_buffer is not None:
            return self.c_buffer[offset : offset + length]

        # load the buffer from file
        if self.__handle is None:
            raise ValueError("no db handle available")
        self.__handle.seek(offset)
        self.__io_count += 1
        return self.__handle.read(length)

    def close(self) -> None:
        if self.__handle is not None:
            self.__handle.close()

    def __str__(self) -> str:
        v_index = None if self.vector_index is None else len(self.vector_index)
        c_buffer = None if self.c_buffer is None else len(self.c_buffer)
        return (
            f'{{"version": {self.version.name}, "db_path": "{self.__db_path}", '
            f'"v_index": {v_index}, "c_buffer": {c_buffer}}}'
        )


# ---
# functions to create Searcher with different cache policy


def new_with_file_only(version: util.Version, db_path: str) -> Searcher:
    return Searcher(version, db_path, None, None)


def new_with_vector_index(
    version: util.Version,
    db_path: str,
    vector_index: bytes,
) -> Searcher:
    return Searcher(version, db_path, vector_index, None)


def new_with_buffer(version: util.Version, c_buffer: bytes) -> Searcher:
    return Searcher(version, None, None, c_buffer)
