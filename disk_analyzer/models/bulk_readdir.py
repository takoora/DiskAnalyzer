"""Fast directory listing using macOS getattrlistbulk() syscall.

Combines readdir + stat into a single kernel call per buffer, returning
name, type, and allocated size for all entries in one shot.
Falls back to os.scandir() if getattrlistbulk is unavailable.
"""
import os
import struct
import ctypes
import sys

# Only available on macOS
_AVAILABLE = sys.platform == "darwin"

if _AVAILABLE:
    try:
        _libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    except OSError:
        _AVAILABLE = False

# getattrlistbulk constants
ATTR_BIT_MAP_COUNT = 5
ATTR_CMN_RETURNED_ATTRS = 0x80000000
ATTR_CMN_NAME = 0x00000001
ATTR_CMN_OBJTYPE = 0x00000008
ATTR_CMN_ERROR = 0x20000000
ATTR_FILE_ALLOCSIZE = 0x00000004

VREG = 1   # regular file
VDIR = 2   # directory
VLNK = 5   # symlink

_BUF_SIZE = 256 * 1024  # 256 KB buffer


class _AttrList(ctypes.Structure):
    _fields_ = [
        ("bitmapcount", ctypes.c_ushort),
        ("reserved", ctypes.c_ushort),
        ("commonattr", ctypes.c_uint),
        ("volattr", ctypes.c_uint),
        ("dirattr", ctypes.c_uint),
        ("fileattr", ctypes.c_uint),
        ("forkattr", ctypes.c_uint),
    ]


def bulk_readdir(dir_path):
    """Read all entries in a directory using getattrlistbulk().

    Returns list of (name: str, is_dir: bool, alloc_size: int).
    Skips symlinks. Raises OSError on failure.
    """
    if not _AVAILABLE:
        return _fallback_readdir(dir_path)

    fd = os.open(dir_path, os.O_RDONLY)
    try:
        al = _AttrList()
        al.bitmapcount = ATTR_BIT_MAP_COUNT
        al.commonattr = (
            ATTR_CMN_RETURNED_ATTRS | ATTR_CMN_NAME |
            ATTR_CMN_OBJTYPE | ATTR_CMN_ERROR
        )
        al.fileattr = ATTR_FILE_ALLOCSIZE

        buf = ctypes.create_string_buffer(_BUF_SIZE)
        results = []

        while True:
            count = _libc.getattrlistbulk(
                fd, ctypes.byref(al), buf, _BUF_SIZE, 0
            )
            if count < 0:
                # syscall error — fall back
                return _fallback_readdir(dir_path)
            if count == 0:
                break

            offset = 0
            raw = buf.raw
            for _ in range(count):
                entry_len = struct.unpack_from("I", raw, offset)[0]
                pos = offset + 4

                # returned attrs bitmaps (5 x uint32)
                ret_common = struct.unpack_from("I", raw, pos)[0]
                ret_file = struct.unpack_from("I", raw, pos + 12)[0]
                pos += 20

                # error attribute (if present)
                if ret_common & ATTR_CMN_ERROR:
                    pos += 4  # skip error code

                # name: attrreference_t (offset, length)
                name_info_off, name_info_len = struct.unpack_from("iI", raw, pos)
                name_start = pos + name_info_off
                name = raw[name_start:name_start + name_info_len - 1].decode(
                    "utf-8", errors="replace"
                )
                pos += 8

                # object type
                obj_type = struct.unpack_from("I", raw, pos)[0]
                pos += 4

                # file alloc size (only for regular files)
                alloc_size = 0
                if ret_file & ATTR_FILE_ALLOCSIZE:
                    alloc_size = struct.unpack_from("q", raw, pos)[0]

                is_dir = obj_type == VDIR
                is_link = obj_type == VLNK

                if not is_link:
                    results.append((name, is_dir, alloc_size))

                offset += entry_len

        return results
    finally:
        os.close(fd)


def _fallback_readdir(dir_path):
    """Fallback using os.scandir() when getattrlistbulk is unavailable."""
    results = []
    with os.scandir(dir_path) as it:
        for entry in it:
            try:
                if entry.is_symlink():
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                if is_dir:
                    results.append((entry.name, True, 0))
                else:
                    try:
                        st = entry.stat(follow_symlinks=False)
                        # st_blocks is not available on Windows
                        size = st.st_blocks * 512 if hasattr(st, "st_blocks") else st.st_size
                    except OSError:
                        size = 0
                    results.append((entry.name, False, size))
            except OSError:
                continue
    return results
