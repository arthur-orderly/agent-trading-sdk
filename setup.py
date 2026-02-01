"""Arthur SDK - Simple trading for AI agents on Orderly Network."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="arthur-sdk",
    version="0.1.0",
    author="Arthur",
    author_email="arthur@orderly.network",
    description="Simple trading for AI agents on Orderly Network",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ranyi1115/arthur-sdk",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pynacl>=1.5.0",  # For ed25519 signing
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "black>=23.0",
            "mypy>=1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "arthur=arthur.cli:main",
        ],
    },
)
