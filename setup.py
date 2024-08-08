from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in po_data_worksheet/__init__.py
from po_data_worksheet import __version__ as version

setup(
	name="po_data_worksheet",
	version=version,
	description="PO data worksheet",
	author="admin",
	author_email="admin@example.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
