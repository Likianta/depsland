import os
import re
from time import time

from lk_logger import lk
from lk_utils import dumps
from pkginfo import SDist
from pkginfo import Wheel

from .data_struct import PackageInfo
from .data_struct import Requirement
from .data_struct.special_versions import LATEST
from .path_model import pypi_model
from .pip import default_pip
from .typehint import *
from .utils import find_best_matched_version
from .utils import sort_versions
from .utils import unzip_file


class LocalPyPI:
    UPDATE_FREQ = 60 * 60 * 24 * 7  # one week
    
    pip: TPip
    
    name_versions: TNameVersions
    locations: TLocationsIndex
    dependencies: TDependenciesIndex
    updates: TUpdates
    
    def __init__(self, pip: TPip):
        self.pip = pip
        a, b, c, d = pypi_model.load_indexed_data()
        self.name_versions = a
        self.locations = b
        self.dependencies = c
        self.updates = d
    
    def analyse_requirement(self, req: TRequirement):
        # if version doesn't in self.name_versions, or the version requests
        # latest but local repository is outdated, we should refresh local
        # repository.
        version = self._get_local_matched_version(req)
        if version:
            lk.loga('found requirement in local repo', req)
            req.set_fixed_version(version)
        else:
            lk.loga('request requirement from pip (online)', req)
            req = self._refresh_local_repo(req)
        
        name, version, name_id = req.name, req.version, req.name_id
        
        return PackageInfo(
            name=name, version=version, name_id=name_id,
            locations=self.locations[name_id],
            dependencies=self.dependencies[name_id]
        )
    
    def get_all_dependencies(self, name_id, holder=None) -> List[TNameId]:
        if holder is None:
            holder = []
        for dep_name_id in self.dependencies[name_id]:
            if dep_name_id in holder:
                continue
            holder.append(dep_name_id)
            self.get_all_dependencies(dep_name_id, holder)
        return holder
    
    def get_locations(self, name_id) -> TLocations:
        return self.locations[name_id]
    
    def _get_local_matched_version(self, req, check_outdated=True):
        """
        
        Notice:
            If returns None, it means:
                a) the requested version doesn't exist in `self.name_versions`.
                b) the version requests latest but the local repository is
                   outdated.
            In case (a) we know that the downloading session is required; in
            case (b) we don't know whether it already exists.
            So the downloader should check whether an incoming 'latest' version
            exists to avoid saving an existed verison which may cause a
            FileExistsError.
        """
        if req.name not in self.name_versions:
            return None
        if req.version_spec == LATEST:
            if check_outdated and self._is_outdated(req.name):
                return None
        version_list = self.name_versions[req.name]
        return find_best_matched_version(req.version_spec, version_list)
    
    def _is_outdated(self, name):
        if t := self.updates.get(name):
            if (time() - t) <= self.UPDATE_FREQ:
                return False
        return True
    
    def _refresh_local_repo(self, req: TRequirement):
        _req = req
        
        deps = {}
        available_namespace = {}
        
        for path in self._download(req.raw_name, pypi_model.downloads):
            if path.endswith(('.whl', '.zip')):
                pkg = Wheel(path)
            elif path.endswith(('.tar.gz', '.tar')):
                pkg = SDist(path)
            else:
                raise Exception('This file type is not recognized', path)
            
            req = Requirement(pkg.name, pkg.version)
            name, version, name_id = req.name, req.version, req.name_id
            
            available_namespace[name] = version
            
            # self.updates
            self.updates[name] = int(time())
            
            # self.name_versions
            if version in self.name_versions[name]:
                lk.loga('local repo satisfies requirement', name_id)
                continue
            else:
                self.name_versions[name].append(version)
                sort_versions(self.name_versions[name])
            
            # self.locations
            try:
                loc = pypi_model.mkdir(name_id)
                unzip_file(path, loc)
            except FileExistsError:
                loc = pypi_model.extraced + '/' + name_id
            finally:
                # noinspection PyUnboundLocalVariable
                self.locations[name_id].append(loc)
                #   FIXME: assign sole location instead of list[location] type
            
            # self.dependencies
            deps[name_id] = pkg.requires_dist
            #   pkg.requires_dist: e.g. 'cachecontrol[filecache] (>=0.12.4,
            #       <0.13.0)', 'cachy (>=0.3.0,<0.4.0)', ...
        
        assert _req.name in available_namespace, (
            _req, available_namespace
        )
        _req.set_fixed_version(available_namespace[_req.name])
        
        for name_id, requires_dist in deps.items():
            for raw_name in requires_dist:
                # # excluded names
                # if re.search(r'\bextra\b *==', raw_name):
                #     lk.loga('exclude extra package', raw_name)
                #     continue
                
                dep = Requirement(raw_name)
                
                if dep.name not in available_namespace:
                    # it means this dep is an invalid package (authorized by
                    # pip download)
                    lk.loga('invalid package recorded in requires_dist but not '
                            'downloaded by pip-download', dep.raw_name)
                    continue
                
                version = available_namespace[dep.name]
                dep.set_fixed_version(version)
                self.dependencies[name_id].append(dep.name_id)
        
        return _req
    
    def _download(self, raw_name, dst_dir):
        """
        Returns:
            Union[path, empty_string]
                path: new downloaded file path
                empty_string: the requested file already exists in local
        """
        lk.loga('downloading package (this takes a few seconds/minutes...)',
                raw_name)
        # use quotes around `raw_name` because `raw_name` includes version
        # specifiers (like '>', '<', etc.) which should be wrapped when using
        # in shell. (https://pip.pypa.io/en/stable/cli/pip_install/#requirement
        # -specifiers)
        ret = self.pip.download(f'"{raw_name}"', dst_dir)
        r'''Example:
            Looking in indexes: https://pypi.tuna.tsinghua.edu.cn/simple
            Collecting lk-utils
              File was already downloaded e:\downloads\test_20210826_155333\lk_u
              tils-1.4.4-py38-none-any.whl
            Collecting lk-logger<4.0,>=3.6
              File was already downloaded e:\downloads\test_20210826_155333\lk_l
              ogger-3.6.3-py3-none-any.whl
            Collecting xlsxwriter<2.0,>=1.3
              File was already downloaded e:\downloads\test_20210826_155333\Xlsx
              Writer-1.4.5-py2.py3-none-any.whl
            Collecting xlrd==1.2
              Using cached https://pypi.tuna.tsinghua.edu.cn/packages/b0/16/6357
              6a1a001752e34bf8ea62e367997530dc553b689356b9879339cf45a4/xlrd-1.2.
              0-py2.py3-none-any.whl (103 kB)
            Saved e:\downloads\test_20210826_155333\xlrd-1.2.0-py2.py3-none-any.
            whl
            Successfully downloaded lk-utils xlrd lk-logger xlsxwriter
        '''
        
        pattern1 = re.compile(r'(?<=Saved ).+')
        pattern2 = re.compile(r'(?<=File was already downloaded ).+')
        
        for m in pattern1.finditer(ret):
            yield m.group()
        
        for m in pattern2.finditer(ret):
            yield m.group()
        
        for m in re.finditer(r'(?<=Saved ).+', ret):
            path = m.group()
            lk.logt('[D0108]', 'new file downloaded', os.path.basename(path))
            yield path
        for m in re.finditer(r'(?<=File was already downloaded ).+', ret):
            path = m.group()
            lk.logt('[D0109]', 'file already exists', os.path.basename(path))
            yield path
    
    def save(self):
        for data, file in zip(
                (self.name_versions,
                 self.locations,
                 self.dependencies,
                 self.updates),
                pypi_model.get_indexed_files()
        ):
            dumps(data, file)


local_pypi = LocalPyPI(default_pip)

__all__ = ['local_pypi']
