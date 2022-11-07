from functools import partial
from os.path import basename

from oss2 import Auth
from oss2 import Bucket


class Oss:
    
    def __init__(self, appid: str,
                 access_key: str, access_secret: str,
                 endpoint: str, bucket_name: str, **_):
        self._auth = Auth(access_key, access_secret)
        self._bucket = Bucket(self._auth, endpoint, bucket_name)
        self._path = OssPath(appid)
    
    @property
    def bucket(self):
        return self._bucket
    
    @property
    def path(self) -> 'OssPath':
        return self._path
    
    def make_link(self, key: str) -> str:
        """ make link for sharing. """
        return self._bucket.sign_url('GET', key, 3600)
    
    def upload(self, file: str, link: str) -> None:
        """
        warning: if target exists, will overwrite.
        """
        name = basename(file)
        # noinspection PyUnusedLocal
        resp = self._bucket.put_object_from_file(
            link, file, progress_callback=partial(
                self._update_progress, f'uploading {name}'
            )
        )
        print(':rpt', f'upload done [cyan]({name})[/]')
    
    def download(self, link: str, file: str) -> None:
        name = basename(file)
        # noinspection PyUnusedLocal
        resp = self._bucket.get_object_to_file(
            link, file, progress_callback=partial(
                self._update_progress, f'downloading {name}'
            )
        )
        print(':rpt', f'download done [cyan]({name})[/]')
    
    def delete(self, link: str) -> None:
        self._bucket.delete_object(link)
    
    @staticmethod
    def _update_progress(
            description: str,
            bytes_consumed: int, total_bytes: int
    ) -> None:
        print('{}: {:.2%}'.format(
            description,
            bytes_consumed / total_bytes
        ), end='\r')


class OssPath:
    
    def __init__(self, appid: str):
        self.appid = appid
    
    def __str__(self):
        return f'<bucket:/depsland/apps/{self.appid}>'
    
    @property
    def manifest(self) -> str:
        return f'apps/{self.appid}/manifest.pkl'
    
    @property
    def assets(self) -> str:
        return f'apps/{self.appid}/assets'
    
    @property
    def pypi(self) -> str:
        return f'apps/{self.appid}/pypi'
