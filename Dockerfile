# Let buildx choose platform (don’t hardcode)
FROM ghcr.io/galoisinc/saw:nightly

# Become root to apt-get
USER root
ENV DEBIAN_FRONTEND=noninteractive

# Tools needed by examples and your workflow
# - clang/llvm-14: matches your earlier choice
# - build-essential/make/findutils: for Makefiles & traversal
# - openjdk-17-jdk: for JVM examples
# - hasktags: fixes `make` TAGS step
# - git: to clone repos (cryptol, specs, etc.)
# - picosat: external SAT solver (used by some examples)
# - python3-pip (optional): if you want Python utilities in-container
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        clang-14 llvm-14 llvm-14-tools \
        build-essential make findutils \
        openjdk-17-jdk ca-certificates \
        hasktags git picosat python3-pip \
        libssl-dev && \
    # create unversioned symlinks expected by many scripts
    ln -sf /usr/bin/clang-14     /usr/bin/clang && \
    ln -sf /usr/bin/clang++-14   /usr/bin/clang++ && \
    ln -sf /usr/bin/llvm-link-14 /usr/bin/llvm-link && \
    ln -sf /usr/bin/llvm-dis-14  /usr/bin/llvm-dis && \
    rm -rf /var/lib/apt/lists/*

# Parallel make
ENV MAKEFLAGS="-j$(nproc)"

# Where we’ll put/check out sources you want available
WORKDIR /workspace

# Helpful environment for Cryptol to find specs you’ll clone under /workspace
# (We’ll point CRYPTOLPATH to these dirs after you clone them.)
ENV CRYPTOLPATH="/workspace/cryptol:/workspace/cryptol-specs:/workspace/cryptol-specs-specs"

# Optional: default solver for external CNF examples
ENV SAW_CNF_SOLVER=picosat

# (Optional) drop back to image’s default user
# USER saw
