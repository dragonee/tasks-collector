from setuptools import setup, find_packages

setup(
    name='tasks_collector_tools',
    version='1.0.0',
    description='CLI support for the Tasks Collector application',
    author='Michał Moroz <michal@makimo.pl>',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    packages=('tasks_collector_tools', 'tasks_collector_tools.config'),
    package_dir={'': 'src'},
    install_requires=['docopt', 'requests', 'python-slugify', 'pyyaml', 'colored', 'more-itertools', 'python-dateutil', 'pydantic', 'aiohttp'],
    python_requires='>=3',
    entry_points={
        'console_scripts': [
            'observation = tasks_collector_tools.observation:main',
            'boardmd = tasks_collector_tools.boardmd:main',
            'observationdump = tasks_collector_tools.observationdump:main',
            'quest = tasks_collector_tools.quest:main',
            'tasks = tasks_collector_tools.tasks:main',
            'update = tasks_collector_tools.update:main',
            'journal = tasks_collector_tools.journal:main',
            'tjournal = tasks_collector_tools.journal:trip_main',
            'tripjournal = tasks_collector_tools.journal:trip_main',
            'habits = tasks_collector_tools.habits:main',
            'eventdump = tasks_collector_tools.eventdump:main',
            'reflectiondump = tasks_collector_tools.reflectiondump:main',
            'reflect = tasks_collector_tools.reflect:main',
            'sjournal = tasks_collector_tools.sjournal:main',
        ],
    }
)
