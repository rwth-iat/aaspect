# syntax=docker/dockerfile:1

# Neo4j Community 5.26 with the DozerDB plugin, which adds CREATE/DROP DATABASE so that
# every analysis gets a database of its own.
FROM graphstack/dozerdb:5.26.27.0@sha256:9b54d6b3a98a76c00bd23e8e78d8c82081ff168162aebd47b25c234e092cb0a0
# APOC in the same patch version as Neo4j, baked in rather than fetched by the image's
# NEO4J_PLUGINS on every start, which would pick whatever version is current.
ADD --chmod=644 \
    --checksum=sha256:59bb2a42376cd3c8c54ccdd804eb974bc71439656aba328fa724e4f65a7d1492 \
    https://github.com/neo4j/apoc/releases/download/5.26.27/apoc-5.26.27-core.jar \
    /var/lib/neo4j/plugins/
