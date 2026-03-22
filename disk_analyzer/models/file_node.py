import os


class FileNode:
    __slots__ = (
        "name", "path", "own_size", "cumulative_size",
        "children", "parent", "is_dir", "extension",
        "file_count", "dir_count", "error",
    )

    def __init__(self, name, path, own_size=0, is_dir=False, parent=None):
        self.name = name
        self.path = path
        self.own_size = own_size
        self.cumulative_size = own_size
        self.children = []
        self.parent = parent
        self.is_dir = is_dir
        self.extension = "" if is_dir else os.path.splitext(name)[1].lower()
        self.file_count = 0 if is_dir else 1
        self.dir_count = 1 if is_dir else 0
        self.error = None

    def add_child_fast(self, child):
        """Append child without propagating cumulative stats (use finalize() after)."""
        child.parent = self
        self.children.append(child)

    def add_child(self, child):
        """Append child and propagate cumulative stats upward one level."""
        child.parent = self
        self.children.append(child)
        self.cumulative_size += child.cumulative_size
        self.file_count += child.file_count
        self.dir_count += child.dir_count

    def finalize(self):
        """Post-order pass to compute cumulative_size, file_count, dir_count."""
        if not self.is_dir:
            return
        self.cumulative_size = self.own_size
        self.file_count = 0
        self.dir_count = 1
        for child in self.children:
            child.finalize()
            self.cumulative_size += child.cumulative_size
            self.file_count += child.file_count
            self.dir_count += child.dir_count

    def sorted_children(self, reverse=True):
        return sorted(self.children, key=lambda c: c.cumulative_size, reverse=reverse)

    def depth(self):
        d = 0
        node = self.parent
        while node is not None:
            d += 1
            node = node.parent
        return d

    def all_files(self):
        if not self.is_dir:
            yield self
        else:
            for child in self.children:
                yield from child.all_files()

    def __repr__(self):
        return f"FileNode({self.name!r}, size={self.cumulative_size}, is_dir={self.is_dir})"
