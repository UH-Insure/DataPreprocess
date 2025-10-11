# Let buildx control platform; don't hardcode here to avoid the warning
FROM ghcr.io/galoisinc/saw:nightly

# Become root to apt-get
USER root
ENV DEBIAN_FRONTEND=noninteractive

# Install toolchain: clang/llvm (versioned) + Java + build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        clang-14 llvm-14 llvm-14-tools \
        build-essential make findutils \
        openjdk-17-jdk ca-certificates && \
    # create unversioned symlinks expected by many scripts
    ln -sf /usr/bin/clang-14     /usr/bin/clang && \
    ln -sf /usr/bin/clang++-14   /usr/bin/clang++ && \
    ln -sf /usr/bin/llvm-link-14 /usr/bin/llvm-link && \
    ln -sf /usr/bin/llvm-dis-14  /usr/bin/llvm-dis && \
    rm -rf /var/lib/apt/lists/*

# Make parallel builds use all cores
ENV MAKEFLAGS="-j$(nproc)"

WORKDIR /workspace
# (Optional) drop back to the image's default user if it defines one
# USER saw
