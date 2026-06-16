# ADR-003: JSON Serialization over Avro

| Attribute | Value |
|-----------|-------|
| **ID** | ADR-003 |
| **Title** | JSON Serialization over Avro |
| **Status** | Accepted |
| **Date** | 2025-01-28 |
| **Owner** | Platform Architecture |

---

## Context

The Sports Platform originally planned to use Apache Avro for message serialization in its Kafka-based data pipeline. This decision was documented in [`plans/avro-pipeline-fix-plan.md`](plans/avro-pipeline-fix-plan.md) and involved:

- **Confluent Schema Registry** for Avro schema management
- **Avro serialization** for Kafka messages
- **Kafka Connect JDBC** to sink data to TimescaleDB

The original motivation for Avro included:

1. **Schema Evolution**: Avro supports backward and forward compatibility for schema changes
2. **Compact Binary Format**: Smaller message sizes compared to JSON
3. **Strong Typing**: Runtime validation of message structure
4. **Kafka Connect Compatibility**: The Confluent JDBC Connector works natively with Avro

However, implementing Avro revealed significant challenges:

- **Python Ecosystem**: Python producers were sending schemaless JSON/bytes, not Avro-encoded records
- **Kafka Connect JDBC Requirement**: The connector requires Avro/Struct format with error: `requires records with a non-null Struct value and non-null Struct schema`
- **Schema Registry Overhead**: Requires additional deployment, management, and monitoring
- **Version Compatibility**: Must maintain schema compatibility across deployments

---

## Decision

**Accepted**: Use JSON serialization with a dual-write pattern instead of Avro serialization.

The platform now uses:

1. **JSON Serialization**: All Kafka messages are serialized as JSON
2. **Direct TimescaleDB Writes**: Application code writes directly to TimescaleDB, bypassing Kafka Connect
3. **Dual-Write Pattern**: Each poll operation writes to both Kafka (for streaming/replay) and TimescaleDB (for persistence)

### Implementation

```python
def serialize_record(transformed: dict[str, Any]) -> bytes:
    """Serialize record to JSON bytes."""
    return json.dumps(transformed).encode("utf-8")

# Dual-write in ResponseHandler
def handle_responses(self, responses: list[dict]):
    # Write to Kafka (streaming/replay)
    self.kafka_producer.send(topic, value=record)
    
    # Write to TimescaleDB (persistence)
    self.timescaledb_writer.insert(record)
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Dual-Write Data Flow Architecture                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Unified Poller / Odds Poller                      │   │
│  └───────────────────────────────────┬─────────────────────────────────┘   │
│                                      │                                        │
│                    ┌─────────────────┼─────────────────┐                    │
│                    ▼                 ▼                 ▼                    │
│            ┌─────────────┐   ┌─────────────┐   ┌─────────────┐             │
│            │   Kafka     │   │ TimescaleDB │   │    Cache    │             │
│            │ (JSON)      │   │ (Direct)    │   │  (Ignite)   │             │
│            └─────────────┘   └─────────────┘   └─────────────┘             │
│                  │                 │                                    │
│            streaming/          persistence                               │
│            replayability                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Consequences

### Benefits

| Aspect | Description |
|--------|-------------|
| **Simplicity** | No Schema Registry deployment, no schema management, no version compatibility concerns |
| **Human-Readable** | JSON messages are easy to debug, inspect, and log |
| **Python Native** | JSON serialization requires no additional libraries beyond the standard library |
| **Direct Persistence** | Bypasses broken Kafka Connect JDBC pipeline entirely |
| **Zero Schema Overhead** | No schema registration, compatibility checks, or evolution planning needed |
| **Faster Development** | No schema definition phase required for new data types |

### Trade-offs

| Aspect | Description |
|--------|-------------|
| **Message Size** | JSON messages are larger than Avro binary format (~2-3x overhead) |
| **No Schema Validation** | Runtime schema errors only caught by consumers, not at serialization |
| **No Schema Evolution** | Breaking changes require coordinated updates across producers and consumers |
| **Less Efficient** | More bandwidth and storage required for high-volume data |

### Mitigations for Trade-offs

1. **Message Size**: Compression (gzip/snappy) can be enabled on Kafka topics if needed
2. **Schema Validation**: Implement JSON Schema validation in consumer code
3. **Schema Evolution**: Use backward-compatible field additions with careful coordination
4. **Storage**: TimescaleDB compression handles large data volumes efficiently

---

## Related

| Document | Relationship |
|----------|--------------|
| [`plans/avro-pipeline-fix-plan.md`](plans/avro-pipeline-fix-plan.md) | Original Avro implementation plan (superseded) |
| [`plans/avro-cleanup-plan.md`](plans/avro-cleanup-plan.md) | Dead Avro code cleanup plan |
| [`AGENTS.md`](AGENTS.md) | Documents dual-write pattern in "Dual-Write Pattern Solves Kafka→TimescaleDB Issues" |
| `src/data_pipeline/producer_config.py` | JSON producer configuration |
| `src/unified_poller/response_handler.py` | Dual-write implementation |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-28 | Platform Architecture | Initial decision record |

---

## References

- [Confluent Kafka Schema Registry Documentation](https://docs.confluent.io/platform/current/schema-registry/index.html)
- [Avro Schema Specification](https://avro.apache.org/docs/current/)
- [FastAVRO Python Library](https://fastavro.readthedocs.io/)
- [Kafka Connect JDBC Connector](https://docs.confluent.io/kafka-connect-jdbc/current/)
