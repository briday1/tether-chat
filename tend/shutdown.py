"""Windows-safe shutdown of an owned tether-chat supervisor and all its subprocesses."""
import subprocess
import psutil

def stop_process_tree(pid,log=print):
    """Stop deepest descendants first so orphaned uvicorn/MCP processes don't linger."""
    try:
        root=psutil.Process(pid)
        descendants=root.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    # Snapshot the owned tree before terminating anything; never select unrelated python processes.
    def depth(proc):
        count=0
        try:
            parent=proc.parent()
            while parent and parent.pid!=root.pid and count<32:
                count+=1
                parent=parent.parent()
        except psutil.Error:pass
        return count
    descendants.sort(key=depth,reverse=True)
    processes=descendants+[root]
    for proc in processes:
        try:
            if proc.is_running():proc.terminate()
        except psutil.NoSuchProcess:pass
        except psutil.Error as exc:log("Terminate "+str(proc.pid)+": "+str(exc))
    _,alive=psutil.wait_procs(processes,timeout=4)
    for proc in alive:
        try:proc.kill()
        except psutil.NoSuchProcess:pass
        except psutil.Error as exc:log("Kill "+str(proc.pid)+": "+str(exc))
    psutil.wait_procs(alive,timeout=3)
    for proc in processes:
        try:
            if proc.is_running() and proc.status()!=psutil.STATUS_ZOMBIE:
                log("tether-chat process still running after exit: "+str(proc.pid))
        except psutil.NoSuchProcess:pass


def stop_child(child,log=print):
    """Use the owned Popen handle as a fallback if process inspection is unavailable."""
    if child is None or child.poll() is not None:return
    try:stop_process_tree(child.pid,log=log)
    except psutil.Error as exc:log("Process inspection unavailable: "+str(exc))
    if child.poll() is None:
        child.terminate()
        try:child.wait(timeout=4)
        except subprocess.TimeoutExpired:
            child.kill();child.wait(timeout=3)
