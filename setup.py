from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="startd8",
    version="0.4.0",
    author="StartDate Contributors",
    author_email="contributors@startdate.dev",
    description="Python SDK for StartDate (startd8) Agent Framework - Multi-LLM benchmarking and prompt management",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/neil-the-nowledgeable/startd8-sdk",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={
        "startd8": [
            "prompt_builder/templates/*.yaml",
            "help_content/*.yaml",
            "concierge_templates/*.md",
            "concierge_templates/inputs/*.yaml",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Environment :: Console",
    ],
    python_requires=">=3.9",
    install_requires=[
        "rich>=13.0.0",
        "pydantic>=2.0.0",
        "typer>=0.9.0",
        "httpx>=0.25.0",
        "questionary>=2.0.0",
        "pyyaml>=6.0.0",
    ],
    extras_require={
        "anthropic": [
            "anthropic>=0.18.0",
        ],
        "openai": [
            "openai>=1.0.0",
        ],
        "all": [
            "anthropic>=0.18.0",
            "openai>=1.0.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
            "hypothesis>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "startd8=startd8.cli:app",
        ],
    },
)

