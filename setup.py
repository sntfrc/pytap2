#!/usr/bin/env python3

import os
import sys

import setuptools

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pytap3_build import PlatformWheel, WintunBuildPy  # noqa: E402

setuptools.setup(
    name="pytap3",
    version="3.1.1",
    description="Cross-platform tunnel interface for Python",
    long_description=open("README.rst").read(),
    keywords=["pytap", "tun", "tap", "networking"],
    author="Federico Santandrea",
    author_email="federico@santandrea.net",
    url="https://github.com/sntfrc/pytap3",
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    package_data={"pytap3": ["py.typed"]},
    cmdclass={"bdist_wheel": PlatformWheel, "build_py": WintunBuildPy},
    entry_points={"console_scripts": ["kisstun=pytap3.kisstun:main"]},
    include_package_data=True,
    python_requires=">=3.8",
    zip_safe=False,
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
