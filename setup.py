# -*- coding: utf-8 -*-

## see https://packaging.python.org/distributing/#setup-py

from setuptools import setup, find_packages
from codecs import open
from os import path

install_requires = ['six', 'numpy', 'scipy', 'pandas', 'matplotlib', 'rwa-python']
extras_require = {} 


pwd = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(pwd, 'README.rst'), encoding='utf-8') as f:
	long_description = f.read()

setup(
	name = 'tramway',
	version = '0.2',
	description = 'TRamWAy',
	long_description = long_description,
	url = 'https://github.com/DecBayComp/TRamWAy',
	author = 'François Laurent',
	author_email = 'francois.laurent@pasteur.fr',
	license = 'CeCILL v2.1',
	#license_holder = 'Institut Pasteur',
	classifiers = [
		'Intended Audience :: Science/Research',
		'Programming Language :: Python :: 2',
		'Programming Language :: Python :: 2.7',
		'Programming Language :: Python :: 3',
		'Programming Language :: Python :: 3.5',
	],
	keywords = '',
	package_dir = {'tramway': 'tramway', 'tramway.demo': 'examples'},
	packages = ['tramway', 'tramway.demo'],
	scripts = ['scripts/tramway', 'scripts/tramway-demo'],
	install_requires = install_requires,
	extras_require = extras_require,
	package_data = {},
)
