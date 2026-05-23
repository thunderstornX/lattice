"""Stand up the LATTICE dashboard for the demo workspace."""

import uvicorn
from lattice.dashboard import create_app

app = create_app("/tmp/lattice_demo_workspace/.lattice/lattice.db")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
