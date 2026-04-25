"""cli-anything-orcaslicer — CLI harness for OrcaSlicer belt printer fork."""

from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-orcaslicer",
    version="1.0.0",
    description="CLI-Anything harness for OrcaSlicer (belt printer fork)",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-orcaslicer=cli_anything.orcaslicer.orcaslicer_cli:cli",
        ],
    },
)
