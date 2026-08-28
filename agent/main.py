import sys

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

from maa.agent.agent_server import AgentServer
from maa.toolkit import Toolkit

import my_action
import my_reco


def main():
    Toolkit.init_option("./")

    if len(sys.argv) < 2:
        print("Usage: python main.py <socket_id>", flush=True)
        print("socket_id is provided by AgentIdentifier.", flush=True)
        sys.exit(1)
        
    socket_id = None
    for arg in sys.argv[1:]:
        if arg.startswith("socket_id="):
            socket_id = arg.split("=", 1)[1]
            break
    if not socket_id:
        socket_id = sys.argv[1]

    print(f"[Agent] 正在连接主程序 Socket: {socket_id}...", flush=True)
    AgentServer.start_up(socket_id)
    print(f"[Agent] 连接成功，自定义动作与巡检识别器已就绪！", flush=True)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()