from __future__ import annotations

import hashlib

import pytest

from taskcontroller.execution.chunking import (
    CHUNKING_PROTOCOL,
    ChunkJoinStatus,
    ChunkPartitionError,
    ChunkPartitioner,
)
from taskcontroller.standards import StandardsSourceRef


def _source(content: str, *, commit: str = "a" * 40, path: str = "src/large.py") -> StandardsSourceRef:
    return StandardsSourceRef(
        repository="owner-repo",
        commit_sha=commit,
        path=path,
        blob_digest="sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _content() -> str:
    return "".join(f"line-{index}\n" for index in range(1, 7))


def test_partitioner_binds_stable_ranges_and_digests_without_raw_content() -> None:
    content = _content()
    source = _source(content)

    partition = ChunkPartitioner(max_lines=2).partition(source, content)

    assert partition.protocol == CHUNKING_PROTOCOL
    assert partition.source_ref == source
    assert [(chunk.range.line_start, chunk.range.line_end) for chunk in partition.chunks] == [
        (1, 2),
        (3, 4),
        (5, 6),
    ]
    assert all(chunk.source_digest == source.blob_digest for chunk in partition.chunks)
    assert all(chunk.content_digest.startswith("sha256:") for chunk in partition.chunks)
    assert all(chunk.chunk_id.startswith("chunk-") for chunk in partition.chunks)
    assert "content" not in partition.to_dict()
    assert all("content" not in chunk.to_dict() for chunk in partition.chunks)


def test_same_source_and_policy_produce_same_manifest_regardless_of_input_ref_object() -> None:
    content = _content()
    first = ChunkPartitioner(max_lines=2).partition(_source(content), content)
    second = ChunkPartitioner(max_lines=2).partition(
        _source(content).to_dict(), content.encode("utf-8")
    )

    assert first.to_dict() == second.to_dict()
    assert first.partition_digest == second.partition_digest


def test_partition_rejects_source_content_digest_drift_before_emitting_chunks() -> None:
    content = _content()
    source = _source(content)

    with pytest.raises(ChunkPartitionError, match="SOURCE_DIGEST_MISMATCH") as exc_info:
        ChunkPartitioner(max_lines=2).partition(source, content + "mutated\n")

    assert exc_info.value.code == "SOURCE_DIGEST_MISMATCH"
    assert exc_info.value.invalidated_child_ids == ()


def test_out_of_order_chunk_inputs_normalize_to_one_join_set() -> None:
    content = _content()
    source = _source(content)
    partitioner = ChunkPartitioner(max_lines=2)
    partition = partitioner.partition(source, content)

    forward = partitioner.join(partition, partition.chunks, current_source=source)
    reverse = partitioner.join(partition, tuple(reversed(partition.chunks)), current_source=source)

    assert forward.status is ChunkJoinStatus.READY
    assert reverse.status is ChunkJoinStatus.READY
    assert forward.normalized_digest == reverse.normalized_digest
    assert tuple(item.chunk_id for item in reverse.normalized_chunks) == tuple(
        item.chunk_id for item in forward.normalized_chunks
    )


def test_chunks_from_different_commit_versions_cannot_join() -> None:
    content = _content()
    old_source = _source(content, commit="a" * 40)
    new_source = _source(content, commit="b" * 40)
    partitioner = ChunkPartitioner(max_lines=2)
    old_partition = partitioner.partition(old_source, content)
    new_partition = partitioner.partition(new_source, content)

    decision = partitioner.join(
        old_partition,
        (*old_partition.chunks[:-1], new_partition.chunks[-1]),
        current_source=new_source,
    )

    assert decision.status is ChunkJoinStatus.BLOCKED
    assert decision.reason_code == "SOURCE_VERSION_MISMATCH"
    assert decision.invalidated_child_ids == tuple(
        chunk.chunk_id for chunk in old_partition.chunks
    )


def test_source_mutation_invalidates_old_child_set_and_blocks_stale_merge() -> None:
    old_content = _content()
    new_content = old_content.replace("line-4", "line-4-mutated")
    old_source = _source(old_content)
    new_source = _source(new_content)
    partitioner = ChunkPartitioner(max_lines=2)
    old_partition = partitioner.partition(old_source, old_content)

    decision = partitioner.join(
        old_partition,
        old_partition.chunks,
        current_source=new_source,
    )

    assert decision.status is ChunkJoinStatus.BLOCKED
    assert decision.reason_code == "SOURCE_VERSION_MISMATCH"
    assert decision.invalidated_child_ids == tuple(
        chunk.chunk_id for chunk in old_partition.chunks
    )
    with pytest.raises(ChunkPartitionError, match="SOURCE_VERSION_MISMATCH"):
        partitioner.require_joinable(
            old_partition,
            old_partition.chunks,
            current_source=new_source,
        )


def test_join_rejects_missing_duplicate_or_foreign_chunk_without_silent_drop() -> None:
    content = _content()
    source = _source(content)
    partitioner = ChunkPartitioner(max_lines=2)
    partition = partitioner.partition(source, content)

    missing = partitioner.join(partition, partition.chunks[:-1], current_source=source)
    duplicate = partitioner.join(
        partition,
        (*partition.chunks[:-1], partition.chunks[-2]),
        current_source=source,
    )
    foreign = partitioner.join(
        partition,
        ({"chunk_id": "chunk-foreign", "source_ref": source.to_dict()},),
        current_source=source,
    )

    assert missing.status is ChunkJoinStatus.BLOCKED
    assert missing.reason_code == "CHUNK_SET_INCOMPLETE"
    assert duplicate.status is ChunkJoinStatus.BLOCKED
    assert duplicate.reason_code == "CHUNK_SET_INVALID"
    assert foreign.status is ChunkJoinStatus.BLOCKED
    assert foreign.reason_code == "CHUNK_SET_INVALID"


def test_partition_round_trip_and_oversized_line_fail_closed() -> None:
    content = _content()
    source = _source(content)
    partitioner = ChunkPartitioner(max_lines=2)
    partition = partitioner.partition(source, content)
    restored = partitioner.from_dict(partition.to_dict())

    assert restored.to_dict() == partition.to_dict()

    oversized = "x" * 32 + "\n"
    with pytest.raises(ChunkPartitionError, match="CHUNK_LIMIT_EXCEEDED"):
        ChunkPartitioner(max_lines=2, max_bytes=8).partition(_source(oversized), oversized)
