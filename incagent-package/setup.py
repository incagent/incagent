from setuptools import setup, find_packages

setup(
    name="incagent",
    version="0.1.0",
    description="Framework for building AI-operated corporations. Wyoming DAO LLC + OpenClaw.",
    author="Incagent DAO LLC",
    author_email="ceo@incagentdao.llc",
    url="https://github.com/incagent/incagent",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        # Core dependencies - AUDITED, trusted sources only
        "pydantic>=2.0",  # Data validation (widely used, audited)
        "requests>=2.28.0",  # HTTP client (trusted)
        "python-dotenv>=0.20.0",  # Environment variable loading (minimal, trusted)
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "black>=22.0",
            "mypy>=0.990",
        ],
        "stripe": [
            "stripe>=5.0.0",  # For payment processing
        ],
    },
    entry_points={
        "console_scripts": [
            "incagent=incagent.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)
