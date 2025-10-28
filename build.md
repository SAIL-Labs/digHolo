# Building digHolo - Complete Instructions

Based on the [digHolo repository](https://github.com/SAIL-Labs/digHolo), here's a complete guide to build the library from scratch.

## Prerequisites

### 1. Install Required Libraries

**On Ubuntu/Debian:**
```bash
# Update package list
sudo apt update

# Install FFTW3 (Fast Fourier Transform library)
sudo apt install libfftw3-dev

# Install Intel MKL (Math Kernel Library)
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneapi.list
sudo apt update
sudo apt install intel-oneapi-mkl-devel

# Install GCC/G++ compiler if not already installed
sudo apt install build-essential
```

### 2. Set Up Environment

```bash
# Source Intel OneAPI environment (needed for compilation)
source /opt/intel/oneapi/setvars.sh
```

## Build the Library

### Option 1: Standalone Build (Embedded Runtime Paths) - RECOMMENDED

This embeds the library paths so you don't need to set environment variables later:

```bash
g++ -std=c++11 -O3 -mavx2 -mfma -fPIC -shared digHolo.cpp -o libdigholo.so \
    -I/opt/intel/oneapi/mkl/latest/include \
    -L/opt/intel/oneapi/mkl/latest/lib/intel64 \
    -lmkl_intel_lp64 -lmkl_sequential -lmkl_core \
    -lpthread -lm -ldl -lfftw3f \
    -Wl,-rpath,/opt/intel/oneapi/mkl/latest/lib/intel64
```

### Option 2: Standard Build (Requires Runtime Environment)

Simpler build, but requires setting `LD_LIBRARY_PATH` at runtime:

```bash
g++ -std=c++11 -O3 -mavx2 -mfma -fPIC -shared digHolo.cpp -o libdigholo.so \
    -I/opt/intel/oneapi/mkl/latest/include \
    -L/opt/intel/oneapi/mkl/latest/lib/intel64 \
    -lmkl_intel_lp64 -lmkl_sequential -lmkl_core \
    -lpthread -lm -ldl -lfftw3f
```

**For Option 2, add this to your `~/.bashrc`:**
```bash
export LD_LIBRARY_PATH=/opt/intel/oneapi/mkl/latest/lib/intel64:$LD_LIBRARY_PATH
```

Then reload: `source ~/.bashrc`

## Verify the Build

Check that all dependencies are resolved:
```bash
ldd libdigholo.so
```

You should see all libraries found (not "not found").

## Usage

See examples.

## Build Flags Explained

- `-std=c++11`: Use C++11 standard
- `-O3`: Maximum optimization
- `-mavx2 -mfma`: Enable AVX2 and FMA CPU instructions for performance
- `-fPIC`: Position Independent Code (required for shared libraries)
- `-shared`: Create a shared library (.so file)
- `-Wl,-rpath`: Embed runtime library search path (makes library standalone)
- `-I`: Include directory for header files
- `-L`: Library directory for linking
- `-l`: Link specific libraries (mkl, fftw3f, pthread, etc.)

## Quick Start (Ubuntu/Debian)

```bash
# Install everything
sudo apt update
sudo apt install libfftw3-dev build-essential
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneapi.list
sudo apt update
sudo apt install intel-oneapi-mkl-devel

# Set up environment
source /opt/intel/oneapi/setvars.sh

# Build (standalone version)
g++ -std=c++11 -O3 -mavx2 -mfma -fPIC -shared digHolo.cpp -o libdigholo.so \
    -I/opt/intel/oneapi/mkl/latest/include \
    -L/opt/intel/oneapi/mkl/latest/lib/intel64 \
    -lmkl_intel_lp64 -lmkl_sequential -lmkl_core \
    -lpthread -lm -ldl -lfftw3f \
    -Wl,-rpath,/opt/intel/oneapi/mkl/latest/lib/intel64

# Verify
ldd libdigholo.so
