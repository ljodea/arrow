# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import absolute_import

import os
import inspect
import posixpath

from os.path import join as pjoin
from six.moves.urllib.parse import urlparse

import pyarrow as pa
from pyarrow.util import implements, _stringify_path, _is_path_like


class FileSystem(object):
    """
    Abstract filesystem interface
    """
    def cat(self, path):
        """
        Return contents of file as a bytes object

        Returns
        -------
        contents : bytes
        """
        with self.open(path, 'rb') as f:
            return f.read()

    def ls(self, path):
        """
        Return list of file paths
        """
        raise NotImplementedError

    def delete(self, path, recursive=False):
        """
        Delete the indicated file or directory

        Parameters
        ----------
        path : string
        recursive : boolean, default False
            If True, also delete child paths for directories
        """
        raise NotImplementedError

    def disk_usage(self, path):
        """
        Compute bytes used by all contents under indicated path in file tree

        Parameters
        ----------
        path : string
            Can be a file path or directory

        Returns
        -------
        usage : int
        """
        path = _stringify_path(path)
        path_info = self.stat(path)
        if path_info['kind'] == 'file':
            return path_info['size']

        total = 0
        for root, directories, files in self.walk(path):
            for child_path in files:
                abspath = self._path_join(root, child_path)
                total += self.stat(abspath)['size']

        return total

    def _path_join(self, *args):
        return self.pathsep.join(args)

    def stat(self, path):
        """

        Returns
        -------
        stat : dict
        """
        raise NotImplementedError('FileSystem.stat')

    def rm(self, path, recursive=False):
        """
        Alias for FileSystem.delete
        """
        return self.delete(path, recursive=recursive)

    def mv(self, path, new_path):
        """
        Alias for FileSystem.rename
        """
        return self.rename(path, new_path)

    def rename(self, path, new_path):
        """
        Rename file, like UNIX mv command

        Parameters
        ----------
        path : string
            Path to alter
        new_path : string
            Path to move to
        """
        raise NotImplementedError('FileSystem.rename')

    def mkdir(self, path, create_parents=True):
        raise NotImplementedError

    def exists(self, path):
        raise NotImplementedError

    def isdir(self, path):
        """
        Return True if path is a directory
        """
        raise NotImplementedError

    def isfile(self, path):
        """
        Return True if path is a file
        """
        raise NotImplementedError

    def _isfilestore(self):
        """
        Returns True if this FileSystem is a unix-style file store with
        directories.
        """
        raise NotImplementedError

    def read_parquet(self, path, columns=None, metadata=None, schema=None,
                     use_threads=True, use_pandas_metadata=False):
        """
        Read Parquet data from path in file system. Can read from a single file
        or a directory of files

        Parameters
        ----------
        path : str
            Single file path or directory
        columns : List[str], optional
            Subset of columns to read
        metadata : pyarrow.parquet.FileMetaData
            Known metadata to validate files against
        schema : pyarrow.parquet.Schema
            Known schema to validate files against. Alternative to metadata
            argument
        use_threads : boolean, default True
            Perform multi-threaded column reads
        use_pandas_metadata : boolean, default False
            If True and file has custom pandas schema metadata, ensure that
            index columns are also loaded

        Returns
        -------
        table : pyarrow.Table
        """
        from pyarrow.parquet import ParquetDataset
        dataset = ParquetDataset(path, schema=schema, metadata=metadata,
                                 filesystem=self)
        return dataset.read(columns=columns, use_threads=use_threads,
                            use_pandas_metadata=use_pandas_metadata)

    def open(self, path, mode='rb'):
        """
        Open file for reading or writing
        """
        raise NotImplementedError

    @property
    def pathsep(self):
        return '/'


class LocalFileSystem(FileSystem):

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = LocalFileSystem()
        return cls._instance

    @implements(FileSystem.ls)
    def ls(self, path):
        path = _stringify_path(path)
        return sorted(pjoin(path, x) for x in os.listdir(path))

    @implements(FileSystem.mkdir)
    def mkdir(self, path, create_parents=True):
        path = _stringify_path(path)
        if create_parents:
            os.makedirs(path)
        else:
            os.mkdir(path)

    @implements(FileSystem.isdir)
    def isdir(self, path):
        path = _stringify_path(path)
        return os.path.isdir(path)

    @implements(FileSystem.isfile)
    def isfile(self, path):
        path = _stringify_path(path)
        return os.path.isfile(path)

    @implements(FileSystem._isfilestore)
    def _isfilestore(self):
        return True

    @implements(FileSystem.exists)
    def exists(self, path):
        path = _stringify_path(path)
        return os.path.exists(path)

    @implements(FileSystem.open)
    def open(self, path, mode='rb'):
        """
        Open file for reading or writing
        """
        path = _stringify_path(path)
        return open(path, mode=mode)

    @property
    def pathsep(self):
        return os.path.sep

    def walk(self, path):
        """
        Directory tree generator, see os.walk
        """
        path = _stringify_path(path)
        return os.walk(path)


class DaskFileSystem(FileSystem):
    """
    Wraps s3fs Dask filesystem implementation like s3fs, gcsfs, etc.
    """

    def __init__(self, fs):
        self.fs = fs

    @implements(FileSystem.isdir)
    def isdir(self, path):
        raise NotImplementedError("Unsupported file system API")

    @implements(FileSystem.isfile)
    def isfile(self, path):
        raise NotImplementedError("Unsupported file system API")

    @implements(FileSystem._isfilestore)
    def _isfilestore(self):
        """
        Object Stores like S3 and GCSFS are based on key lookups, not true
        file-paths
        """
        return False

    @implements(FileSystem.delete)
    def delete(self, path, recursive=False):
        path = _stringify_path(path)
        return self.fs.rm(path, recursive=recursive)

    @implements(FileSystem.exists)
    def exists(self, path):
        path = _stringify_path(path)
        return self.fs.exists(path)

    @implements(FileSystem.mkdir)
    def mkdir(self, path, create_parents=True):
        path = _stringify_path(path)
        if create_parents:
            return self.fs.mkdirs(path)
        else:
            return self.fs.mkdir(path)

    @implements(FileSystem.open)
    def open(self, path, mode='rb'):
        """
        Open file for reading or writing
        """
        path = _stringify_path(path)
        return self.fs.open(path, mode=mode)

    def ls(self, path, detail=False):
        path = _stringify_path(path)
        return self.fs.ls(path, detail=detail)

    def walk(self, path):
        """
        Directory tree generator, like os.walk
        """
        path = _stringify_path(path)
        return self.fs.walk(path)


class S3FSWrapper(DaskFileSystem):

    @implements(FileSystem.isdir)
    def isdir(self, path):
        path = _sanitize_s3(_stringify_path(path))
        try:
            contents = self.fs.ls(path)
            if len(contents) == 1 and contents[0] == path:
                return False
            else:
                return True
        except OSError:
            return False

    @implements(FileSystem.isfile)
    def isfile(self, path):
        path = _sanitize_s3(_stringify_path(path))
        try:
            contents = self.fs.ls(path)
            return len(contents) == 1 and contents[0] == path
        except OSError:
            return False

    def walk(self, path, refresh=False):
        """
        Directory tree generator, like os.walk

        Generator version of what is in s3fs, which yields a flattened list of
        files
        """
        path = _sanitize_s3(_stringify_path(path))
        directories = set()
        files = set()

        for key in list(self.fs._ls(path, refresh=refresh)):
            path = key['Key']
            if key['StorageClass'] == 'DIRECTORY':
                directories.add(path)
            elif key['StorageClass'] == 'BUCKET':
                pass
            else:
                files.add(path)

        # s3fs creates duplicate 'DIRECTORY' entries
        files = sorted([posixpath.split(f)[1] for f in files
                        if f not in directories])
        directories = sorted([posixpath.split(x)[1]
                              for x in directories])

        yield path, directories, files

        for directory in directories:
            for tup in self.walk(directory, refresh=refresh):
                yield tup


def _sanitize_s3(path):
    if path.startswith('s3://'):
        return path.replace('s3://', '')
    else:
        return path


def _ensure_filesystem(fs):
    fs_type = type(fs)

    # If the arrow filesystem was subclassed, assume it supports the full
    # interface and return it
    if not issubclass(fs_type, FileSystem):
        for mro in inspect.getmro(fs_type):
            if mro.__name__ == 'S3FileSystem':
                return S3FSWrapper(fs)
            # In case its a simple LocalFileSystem (e.g. dask) use native arrow
            # FS
            elif mro.__name__ == 'LocalFileSystem':
                return LocalFileSystem.get_instance()

        raise IOError('Unrecognized filesystem: {0}'.format(fs_type))
    else:
        return fs


def resolve_filesystem_and_path(where, filesystem=None):
    """
    Return filesystem from path which could be an HDFS URI, a local URI,
    or a plain filesystem path.
    """
    if not _is_path_like(where):
        if filesystem is not None:
            raise ValueError("filesystem passed but where is file-like, so"
                             " there is nothing to open with filesystem.")
        return filesystem, where

    path = _stringify_path(where)

    if filesystem is not None:
        return _ensure_filesystem(filesystem), path

    parsed_uri = urlparse(path)
    if parsed_uri.scheme == 'hdfs' or parsed_uri.scheme == 'viewfs':
        # Input is hdfs URI such as hdfs://host:port/myfile.parquet
        netloc_split = parsed_uri.netloc.split(':')
        host = netloc_split[0]
        if host == '':
            host = 'default'
        else:
            host = parsed_uri.scheme + "://" + host
        port = 0
        if len(netloc_split) == 2 and netloc_split[1].isnumeric():
            port = int(netloc_split[1])
        fs = pa.hdfs.connect(host=host, port=port)
        fs_path = parsed_uri.path
    elif parsed_uri.scheme == 'file':
        # Input is local URI such as file:///home/user/myfile.parquet
        fs = LocalFileSystem.get_instance()
        fs_path = parsed_uri.path
    else:
        # Input is local path such as /home/user/myfile.parquet
        fs = LocalFileSystem.get_instance()
        fs_path = where

    return fs, fs_path
