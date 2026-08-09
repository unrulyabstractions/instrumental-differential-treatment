# script/remote/capture

The capture gate and the two tools it stands on. Nothing here destroys a box
until its own gate has exited 0, read directly and never through a pipe.

| File | Responsibility |
|---|---|
| `gate_and_destroy_boxes.sh` | Run the capture gate on every box this project owns, and destroy a box only if its own gate exited 0. |
| `verify_remote_capture.py` | Prove every file on a rented box is already local, before the box is destroyed. |
| `list_instances.py` | List my boxes from the registry, and fail loudly if any cannot be accounted for. |
