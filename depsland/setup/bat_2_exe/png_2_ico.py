"""
Convert jpg, png, etc. to ico.

Requirements:
    pillow
    
BTW: You can find a convertion tool online, for example this site:
    https://www.easyicon.net/covert/
"""
from os.path import splitext


def dialog():
    file_i = input('image: ')
    file_o = splitext(file_i)[0] + '.ico'
    png_2_ico(file_i, file_o)


def png_2_ico(file_i, file_o):
    try:
        # noinspection PyPackageRequirements
        from PIL import Image  # pip install pillow
    except ImportError as e:
        print('Please install pillow library (pip install pillow)')
        raise e
    img = Image.open(file_i)
    img.save(file_o)
    img.close()


if __name__ == '__main__':
    dialog()
