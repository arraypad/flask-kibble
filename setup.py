#!/usr/bin/env python

import os
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name='flask-kibble',
    version='0.0.1',
    description='Admin interface library for appengine.',
    long_description=read('README.md'),
    author='Chris Targett',
    author_email='chris@xlevus.net',
    url='http://github.com/xlevus/flask-kibble',
    packages=['flask_kibble', 'flask_kibble.util'],
    install_requires=['flask', 'wtforms>=2.0.0', 'wtforms-ndb>=0.0.2'],
    classifiers=[
    ],
    keywords='flask wtforms appengine ndb',
    license='',
    test_suite='nose.collector',
    tests_require=['nose', 'flask-testing', 'mock', 'flask-gae'],
)
