import re
import sys
import typing as t

from lk_utils import fs
from lk_utils import loads
from lk_utils import run_cmd_args

from ..normalization import normalize_name


class T:
    ExactVersion = str
    PackageId = str  # str['{name}-{version}']
    PackageName = str
    
    # DependenciesTree0 = t.Dict[PackageName, t.Iterable[PackageName]]
    # DependenciesTree1 = t.Dict[PackageId, t.Sequence[PackageId]]
    # DependenciesTree = t.Dict[PackageId, t.Sequence[PackageId]]
    # Name2Id = t.Dict[PackageName, PackageId]
    # Name2Version = t.Dict[PackageName, ExactVersion]
    
    # noinspection PyTypedDict
    PackageInfo = t.TypedDict('PackageInfo', {
        'id'      : PackageId,
        'name'    : PackageName,
        'version' : ExactVersion,
        # 'dependencies': t.Sequence[PackageId],
        'appendix': t.TypedDict('Appendix', {
            'custom_url': str,
        }, total=False)
    })
    
    # Packages = t.Dict[PackageId, PackageInfo]
    Packages = t.Dict[PackageName, PackageInfo]


def resolve_poetry_lock(pyproj_file: str, poetry_file: str) -> T.Packages:
    pyproj_data = loads(pyproj_file, 'toml')
    poetry_data = loads(poetry_file, 'toml')
    
    all_pkgs = _get_all_packages(poetry_data)
    all_pkgs = _flatten_dependencies({k: tuple(v) for k, v in all_pkgs})
    tiled_pkgs = _get_tiled_packages(fs.parent(poetry_file))
    tiled_pkgs = _filter_packages(all_pkgs, dict(tiled_pkgs))
    
    pkgs_info = _fill_packages_info(tuple(tiled_pkgs), poetry_data)
    return dict(pkgs_info)


def _get_all_packages(
    poetry_data: dict
) -> t.Iterator[t.Tuple[T.PackageName, t.Iterable[T.PackageName]]]:
    for item in poetry_data['package']:
        name = normalize_name(item['name'])
        # ver = item['version']
        deps = item.get('dependencies', {})
        yield name, map(normalize_name, deps.keys())


def _flatten_dependencies(
    all_pkgs: t.Dict[T.PackageName, t.Tuple[T.PackageName, ...]]
) -> t.Iterator[t.Tuple[T.PackageName, t.Iterable[T.PackageName]]]:
    def recurse(key: str, _recorded: set = None) -> t.Iterator[T.PackageName]:
        if _recorded is None:
            _recorded = set()
        for dep_name in all_pkgs[key]:
            if dep_name not in _recorded:
                _recorded.add(dep_name)
                yield dep_name
                yield from recurse(dep_name, _recorded)
    
    for key in all_pkgs:
        yield key, recurse(key)


def _get_tiled_packages(
    working_root: str
) -> t.Iterator[t.Tuple[T.PackageName, T.ExactVersion]]:
    content: str = run_cmd_args(
        (sys.executable, '-m', 'poetry'),
        ('show', '--no-ansi'),
        ('--directory', working_root),
    )
    pattern = re.compile(r'([^ ]+) +(?:\(!\) )?([^ ]+)')
    for line in content.splitlines():
        # print(':vi2', line)
        name, ver = pattern.match(line).groups()
        name = normalize_name(name)
        yield name, ver


def _filter_packages(
    all_pkgs: t.Iterator[t.Tuple[T.PackageName, t.Iterable[T.PackageName]]],
    tiled_pkgs: t.Dict[T.PackageName, T.ExactVersion]
) -> t.Iterator[T.PackageId]:
    for name, _ in all_pkgs:
        if name in tiled_pkgs:
            yield f'{name}-{tiled_pkgs[name]}'


def _fill_packages_info(
    tiled_pkgs: t.Tuple[T.PackageId, ...],
    poetry_data: dict
) -> t.Iterator[t.Tuple[T.PackageName, T.PackageInfo]]:
    def get_custom_url() -> t.Optional[str]:
        if item['source']['type'] == 'legacy':  # TEST
            if item['source']['reference'] == 'likianta-hosted':
                return '{}/{}/{}'.format(
                    item['source']['url'],
                    name,
                    item['files'][0]['file']
                )
            
    for item in poetry_data['package']:
        name = normalize_name(item['name'])
        ver = item['version']
        id = f'{name}-{ver}'
        if id in tiled_pkgs:
            info: T.PackageInfo = {
                'id'      : id,
                'name'    : name,
                'version' : ver,
                'appendix': (
                    (custom_url := get_custom_url()) and
                    {'custom_url': custom_url} or {})
            }
            yield name, info


# -----------------------------------------------------------------------------
# DELETE

def _filter_dependencies(
    pkgs: t.Iterator[t.Tuple[T.PackageName, t.Iterable[T.PackageName]]],
    tiled_pkgs: dict
) -> t.Iterator[t.Tuple[T.PackageId, t.Tuple[T.PackageId, ...]]]:
    # print(tiled_pkgs, ':lv')
    # exit(0)
    
    for top_name, deps in pkgs:
        top_ver = tiled_pkgs[top_name]
        top_id = f'{top_name}-{top_ver}'
        
        filtered_deps = []
        for dep_name in deps:
            if dep_name in tiled_pkgs:
                dep_ver = tiled_pkgs[dep_name]
                dep_id = f'{dep_name}-{dep_ver}'
                filtered_deps.append(dep_id)
        
        yield top_id, tuple(sorted(filtered_deps))


# def _filter_top_packages(
#     all_pkgs: t.Iterator[t.Tuple[T.PackageName, t.Iterable[T.PackageName]]],
#     top_names: t.Tuple[T.PackageName, ...]
# ) -> t.Iterator[t.Tuple[T.PackageName, t.Iterable[T.PackageName]]]:
#     for name, deps in all_pkgs:
#         if name in top_names:
#             yield name, deps


def _flatten_packages(
    pkgs_dict: t.Dict[T.PackageId, t.Tuple[T.PackageId, ...]]
) -> t.Set[T.PackageId]:
    def recurse(key: str) -> t.Iterator[T.PackageId]:
        for dep_id in pkgs_dict[key]:
            if dep_id not in recorded:
                recorded.add(dep_id)
                yield dep_id
                yield from recurse(dep_id)
    
    recorded = set(pkgs_dict.keys())
    for key in pkgs_dict.keys():
        for _ in recurse(key):
            pass
    return recorded


def _get_top_package_names(
    working_root: str, pyproj_data: dict
) -> t.Iterator[T.PackageName]:
    dev_group_names = tuple(
        normalize_name(x)
        for x in pyproj_data
        ['tool']['poetry']['group']['dev']['dependencies'].keys()
    )
    content: str = run_cmd_args(
        (sys.executable, '-m', 'poetry'),
        ('show', '-t', '--no-ansi'),
        ('--directory', working_root),
    )
    pattern = re.compile(r'^[-\w]+')
    for line in content.splitlines():
        if line.startswith((' ', '│', '├', '└')):
            continue
        # print(':vi2', line, bool(pattern.match(line)))
        if m := pattern.match(line):
            top_name = normalize_name(m.group())
            if top_name not in dev_group_names:
                yield top_name
