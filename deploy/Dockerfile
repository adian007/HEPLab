# heplab-base — Phase 0 skeleton (ADR-0008).
# The Tier-1 Rust kernels (ADR-0010) install as optional wheels:
#   pip install heplab[kernels]
# The PYTHIA8/DELPHES sim image (heplab-sim) is layered separately in Phase 3.

FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /dist .

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
ENTRYPOINT ["heplab"]
CMD ["version"]
