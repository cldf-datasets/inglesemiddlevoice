from setuptools import setup


setup(
    name='cldfbench_inglesemiddlevoice',
    py_modules=['cldfbench_inglesemiddlevoice'],
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'cldfbench.dataset': [
            'inglesemiddlevoice=cldfbench_inglesemiddlevoice:Dataset',
        ]
    },
    install_requires=[
        'cldfbench[glottolog]',
        'simplepybtex',
    ],
    extras_require={
        'test': [
            'pytest-cldf',
        ],
    },
)
