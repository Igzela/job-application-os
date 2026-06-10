from setuptools import setup, find_packages

setup(
    name="job-application-os",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "job=jobos.cli:main",
        ],
    },
    python_requires=">=3.8",
)
