import atexit
import typing as t
from collections import defaultdict

from lk_utils import dumps
from lk_utils import fs
from lk_utils import loads

from ..depsolver import T as T0
from ..normalization import split_filename_of_package
from ..paths import pypi as pypi_paths
from ..verspec import sort_versions

_root = pypi_paths.root


class T(T0):
    AbsPath = RelPath = str
    #   relative to `paths.pypi.root`
    Id2Paths = t.Dict[T0.PackageId, t.Tuple[RelPath, RelPath]]
    #   {package_id: (download_path, install_path), ...}
    Name2Versions = t.Dict[T0.PackageName, t.List[T0.ExactVersion]]
    #   versions are sorted in descending order (from new to old).


class Index:
    id_2_paths: T.Id2Paths
    name_2_vers: T.Name2Versions
    _changed: t.Set[T.PackageName]
    _stash_downloads: t.Dict[T0.PackageId, T.AbsPath]
    
    def __init__(self) -> None:
        self.load_index()
        self._changed = set()
        self._stash_downloads = {}
        atexit.register(self.save_index)
    
    # def __contains__(self, item: t.Union[T.PackageName, T.PackageId]) -> bool:
    #     return item in self.name_2_ids or item in self.id_2_paths
    
    # def __contains__(self, item: T.PackageId) -> bool:
    #     return item in self.id_2_paths
    
    def __getitem__(self, id: T.PackageId) -> t.Tuple[T.AbsPath, T.AbsPath]:
        a, b = self.id_2_paths[id]
        return f'{_root}/{a}', f'{_root}/{b}'
    
    def has_name(self, item: T.PackageName) -> bool:
        return item in self.name_2_vers
    
    def has_id(self, item: T.PackageId) -> bool:
        return item in self.id_2_paths
    
    def load_index(self) -> None:
        """
        the initial files were generated by `build/self_build.py:init_pypi_index`
        """
        self.id_2_paths = loads(pypi_paths.id_2_paths)
        # self.id_2_paths = {
        #   k: tuple(v) for k, v in loads(pypi_paths.id_2_paths).items()}
        self.name_2_vers = defaultdict(list)
        self.name_2_vers.update(loads(pypi_paths.name_2_vers))
    
    def add_to_index(self, path: T.AbsPath, type: int) -> None:
        if type == 0:
            name, ver = split_filename_of_package(fs.basename(path))
            # print('stash download', f'{name}-{ver}', ':vp')
            self._stash_downloads[f'{name}-{ver}'] = path
        else:
            _, name, ver = path.rsplit('/', 2)
            try:
                # print('retrieve download', f'{name}-{ver}', ':vp')
                dl_path = self._stash_downloads.pop(f'{name}-{ver}')
            except KeyError:
                print(f'{name}-{ver}', self._stash_downloads, ':lv4')
                exit(1)
            self.update_index(f'{name}-{ver}', dl_path, path)
    
    def update_index(
        self,
        pkg_id: T.PackageId,
        dl_path: T.AbsPath,
        ins_path: T.AbsPath,
        force: bool = False,
    ) -> None:
        if pkg_id in self.id_2_paths and not force:
            return
        assert (
            dl_path.lower().startswith(pypi_paths.downloads.lower())
            #   why use `lower`: the `internal_path` was from pip downloading \
            #   process. in windows its case is not stable.
            #   for examples:
            #       'c:\myname\projects\depsland\pypi\...'
            #       'C:\MyName\projects\depsland\pypi\...'
            and fs.isfile(dl_path)
        )
        assert (
            ins_path.startswith(pypi_paths.installed)
            #   we no need to use `lower` here because the `internal_path` was \
            #   generated by `self.get_install_path`, which is stable.
            and fs.isdir(ins_path)
        )
        self.id_2_paths[pkg_id] = (
            fs.relpath(dl_path, _root),
            fs.relpath(ins_path, _root),
        )
        name, ver = pkg_id.split('-', 1)
        self.name_2_vers[name].append(ver)
        self._changed.add(name)
    
    def save_index(self) -> None:
        if self._stash_downloads:
            print(self._stash_downloads, ':lv3')
            print(
                'there were {} packages downloaded but not installed'
                .format(len(self._stash_downloads)),
                'you can use `sidework/pypi_index.py:rebuild` to fix the '
                'indexes',
                ':v3'
            )
        if self._changed:
            for name in self._changed:
                print('refresh versions stack', name, ':i2vs')
                vers = self.name_2_vers[name]
                sort_versions(vers, reverse=True)
            self._changed.clear()
            dumps(self.id_2_paths, pypi_paths.id_2_paths)
            dumps(self.name_2_vers, pypi_paths.name_2_vers)
            print('saved pypi indexes')
