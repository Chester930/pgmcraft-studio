import os

import app


if __name__ == "__main__":
    allowed_drives = [f"{drive}:\\" for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{drive}:\\")]
    app.demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        allowed_paths=[app.DEFAULT_OUTPUT_DIR] + allowed_drives,
    )
