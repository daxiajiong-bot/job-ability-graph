"""Compatibility metadata for older pip/setuptools build frontends."""

from setuptools import find_packages, setup


setup(
    name="jd-resume-match",
    version="0.1.0",
    description=(
        "JD and resume embedding, hard-negative mining, "
        "and dual-encoder training"
    ),
    python_requires=">=3.9",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=[
        "accelerate>=1.10,<2",
        "datasets>=4.5,<5",
        "huggingface-hub>=0.36,<1",
        "numpy>=2.0,<3",
        "peft>=0.17,<1",
        "PyYAML>=6,<7",
        "safetensors>=0.5,<1",
        "scikit-learn>=1.6,<2",
        "scipy>=1.13,<2",
        "sentence-transformers>=5.1,<6",
        "transformers>=4.57,<5",
    ],
    extras_require={
        "qlora": ["bitsandbytes>=0.46,<1"],
        "dev": ["build>=1.2,<2"],
    },
    entry_points={
        "console_scripts": ["jdmatch=jd_resume_pipeline.cli:main"]
    },
)
