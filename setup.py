#!/usr/bin/env python3

import setuptools

setuptools.setup(
    name="pytap2",
    version="2.4.0",
    description=" Cross-platform version of pytap2",
    long_description=open("README.rst").read(),
    keywords=["pytap", "tun", "tap", "networking"],
    author="Federico Santandrea",
    author_email="federico@santandrea.net",
    url="https://github.com/sntfrc/pytap2",
    packages=setuptools.find_packages("src"),
    package_dir={"": "src"},
    package_data={"pytap2": ["py.typed"]},
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
