from setuptools import find_packages, Extension, dist

try:
    from setuptools import setup
except:
    from distutils.core import setup

import os

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

path = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(path, "requirements.txt")) as fp:
    install_requires = fp.read().strip().split("\n")

VERSION = "0.1.1"
LICENSE = 'MIT'
setup(
    version=VERSION,
    install_requires=install_requires,
    name='size_constrained_clustering',
    description='Size Constrained Clustering solver',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/jingw2/size_constrained_clustering',
    author='Jing Wang',
    author_email='jingw2@foxmail.com',
    license=LICENSE,
    packages=find_packages(),
    python_requires='>=3.6')
