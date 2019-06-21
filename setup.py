import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="SubSeaPro",
    version="0.1.0",
    author="Simon Ball",
    author_email="simon.ball@ntnu.no",
    description="Server/client for queuing jobs onto a calculation server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/simon-ball/SubSeaPro",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPLv3",
        "Operating System :: OS Independent",
    ]
)