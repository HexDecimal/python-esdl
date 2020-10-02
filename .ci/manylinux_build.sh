#!/bin/sh
# Script meant to be run within a manylinux docker environment.
set -e -u -x

PYTHON="/opt/python/$PYVERSION/bin/python"

# Prevent issues with file permissions.
umask 000

# Switch to the project directory.
cd /io

# Install the SDL2 dependancy.
yum install -y SDL2-devel

# Install the Python requirements.
$PYTHON -m pip install -r requirements.txt

# Build the ABI3 wheel.
$PYTHON ./setup.py bdist_wheel --py-limited-api cp35

# Repair the wheel.
auditwheel show dist/*-cp*-abi3-*.whl
auditwheel repair --plat "$PLAT" dist/*-cp*-abi3-*.whl

# Replace dist with the fixed wheels.
rm -f dist/*-cp*-abi3-*.whl
mv wheelhouse/*.whl dist/
