from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PodSpec(_message.Message):
    __slots__ = ("uid", "name", "namespace", "cpu_cores_requested", "memory_gb_requested", "workload_type")
    UID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    CPU_CORES_REQUESTED_FIELD_NUMBER: _ClassVar[int]
    MEMORY_GB_REQUESTED_FIELD_NUMBER: _ClassVar[int]
    WORKLOAD_TYPE_FIELD_NUMBER: _ClassVar[int]
    uid: str
    name: str
    namespace: str
    cpu_cores_requested: float
    memory_gb_requested: float
    workload_type: str
    def __init__(self, uid: _Optional[str] = ..., name: _Optional[str] = ..., namespace: _Optional[str] = ..., cpu_cores_requested: _Optional[float] = ..., memory_gb_requested: _Optional[float] = ..., workload_type: _Optional[str] = ...) -> None: ...

class NodeCandidate(_message.Message):
    __slots__ = ("node_id", "allocatable_cpu", "allocatable_memory_gb", "scheduler_expected_free_cpu", "scheduler_expected_free_memory_gb", "reported_allocatable_cpu", "reported_used_cpu", "reported_free_cpu", "reported_allocatable_memory_gb", "reported_used_memory_gb", "reported_free_memory_gb", "last_heartbeat_timestamp", "recent_heartbeat_intervals")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    ALLOCATABLE_CPU_FIELD_NUMBER: _ClassVar[int]
    ALLOCATABLE_MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    SCHEDULER_EXPECTED_FREE_CPU_FIELD_NUMBER: _ClassVar[int]
    SCHEDULER_EXPECTED_FREE_MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    REPORTED_ALLOCATABLE_CPU_FIELD_NUMBER: _ClassVar[int]
    REPORTED_USED_CPU_FIELD_NUMBER: _ClassVar[int]
    REPORTED_FREE_CPU_FIELD_NUMBER: _ClassVar[int]
    REPORTED_ALLOCATABLE_MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    REPORTED_USED_MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    REPORTED_FREE_MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARTBEAT_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    RECENT_HEARTBEAT_INTERVALS_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    allocatable_cpu: float
    allocatable_memory_gb: float
    scheduler_expected_free_cpu: float
    scheduler_expected_free_memory_gb: float
    reported_allocatable_cpu: float
    reported_used_cpu: float
    reported_free_cpu: float
    reported_allocatable_memory_gb: float
    reported_used_memory_gb: float
    reported_free_memory_gb: float
    last_heartbeat_timestamp: float
    recent_heartbeat_intervals: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, node_id: _Optional[str] = ..., allocatable_cpu: _Optional[float] = ..., allocatable_memory_gb: _Optional[float] = ..., scheduler_expected_free_cpu: _Optional[float] = ..., scheduler_expected_free_memory_gb: _Optional[float] = ..., reported_allocatable_cpu: _Optional[float] = ..., reported_used_cpu: _Optional[float] = ..., reported_free_cpu: _Optional[float] = ..., reported_allocatable_memory_gb: _Optional[float] = ..., reported_used_memory_gb: _Optional[float] = ..., reported_free_memory_gb: _Optional[float] = ..., last_heartbeat_timestamp: _Optional[float] = ..., recent_heartbeat_intervals: _Optional[_Iterable[float]] = ...) -> None: ...

class ScoreRequest(_message.Message):
    __slots__ = ("pod", "nodes", "gamma")
    POD_FIELD_NUMBER: _ClassVar[int]
    NODES_FIELD_NUMBER: _ClassVar[int]
    GAMMA_FIELD_NUMBER: _ClassVar[int]
    pod: PodSpec
    nodes: _containers.RepeatedCompositeFieldContainer[NodeCandidate]
    gamma: float
    def __init__(self, pod: _Optional[_Union[PodSpec, _Mapping]] = ..., nodes: _Optional[_Iterable[_Union[NodeCandidate, _Mapping]]] = ..., gamma: _Optional[float] = ...) -> None: ...

class NodeScore(_message.Message):
    __slots__ = ("node_id", "eta", "confidence", "final_score")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    ETA_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    FINAL_SCORE_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    eta: float
    confidence: float
    final_score: float
    def __init__(self, node_id: _Optional[str] = ..., eta: _Optional[float] = ..., confidence: _Optional[float] = ..., final_score: _Optional[float] = ...) -> None: ...

class ScoreResponse(_message.Message):
    __slots__ = ("scores",)
    SCORES_FIELD_NUMBER: _ClassVar[int]
    scores: _containers.RepeatedCompositeFieldContainer[NodeScore]
    def __init__(self, scores: _Optional[_Iterable[_Union[NodeScore, _Mapping]]] = ...) -> None: ...

class PlacementCommittedRequest(_message.Message):
    __slots__ = ("pod_uid", "node_id", "success")
    POD_UID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    pod_uid: str
    node_id: str
    success: bool
    def __init__(self, pod_uid: _Optional[str] = ..., node_id: _Optional[str] = ..., success: bool = ...) -> None: ...

class PlacementCommittedResponse(_message.Message):
    __slots__ = ("acknowledged",)
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    def __init__(self, acknowledged: bool = ...) -> None: ...
