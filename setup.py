from setuptools import setup, find_packages
from os import path

with open('README.md') as readme_file:
    readme = readme_file.read()


here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'requirements.txt')) as f:
requirements = f.read().split()

setup(
    name="ssp",
    version="0.1.0",
    author="Simon Ball",
    author_email="simon.ball@ntnu.no",
    description="Server/client for queuing jobs onto a calculation server",
    long_description=readme,
    long_description_content_type="text/markdown",
    url="https://github.com/simon-ball/SubSeaPro",
	classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPLv3",
        "Operating System :: OS Independent",
    ],
	install_requires=requirements,
	include_package_data=True,
    packages=find_packages(),    
)