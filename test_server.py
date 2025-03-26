import grpc
from concurrent import futures
import time
from chat_system.proto import raft_pb2, raft_pb2_grpc

class SimpleRaftService(raft_pb2_grpc.RaftServiceServicer):
    def GetLeader(self, request, context):
        return raft_pb2.GetLeaderResponse(
            leaderId="test_server",
            leaderAddress="localhost:50051"
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    raft_pb2_grpc.add_RaftServiceServicer_to_server(SimpleRaftService(), server)
    server.add_insecure_port('localhost:50051')
    server.start()
    print("Server started on localhost:50051")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve() 