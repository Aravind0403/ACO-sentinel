import grpc
from typing import Any
import sentinel_pb2

class ACOPredictiveSchedulerStub:
    def __init__(self, channel: grpc.Channel) -> None: ...
    ScoreNodes: grpc.UnaryUnaryMultiCallable[sentinel_pb2.ScoreRequest, sentinel_pb2.ScoreResponse]
    PlacementCommitted: grpc.UnaryUnaryMultiCallable[sentinel_pb2.PlacementCommittedRequest, sentinel_pb2.PlacementCommittedResponse]

class ACOPredictiveSchedulerServicer:
    def ScoreNodes(
        self,
        request: sentinel_pb2.ScoreRequest,
        context: grpc.ServicerContext,
    ) -> sentinel_pb2.ScoreResponse: ...
    def PlacementCommitted(
        self,
        request: sentinel_pb2.PlacementCommittedRequest,
        context: grpc.ServicerContext,
    ) -> sentinel_pb2.PlacementCommittedResponse: ...

def add_ACOPredictiveSchedulerServicer_to_server(
    servicer: ACOPredictiveSchedulerServicer,
    server: grpc.Server,
) -> None: ...

class ACOPredictiveScheduler:
    @staticmethod
    def ScoreNodes(
        request: sentinel_pb2.ScoreRequest,
        target: str,
        options: Any = ...,
        channel_credentials: Any = ...,
        call_credentials: Any = ...,
        insecure: bool = ...,
        compression: Any = ...,
        wait_for_ready: Any = ...,
        timeout: Any = ...,
        metadata: Any = ...,
    ) -> sentinel_pb2.ScoreResponse: ...
    @staticmethod
    def PlacementCommitted(
        request: sentinel_pb2.PlacementCommittedRequest,
        target: str,
        options: Any = ...,
        channel_credentials: Any = ...,
        call_credentials: Any = ...,
        insecure: bool = ...,
        compression: Any = ...,
        wait_for_ready: Any = ...,
        timeout: Any = ...,
        metadata: Any = ...,
    ) -> sentinel_pb2.PlacementCommittedResponse: ...
