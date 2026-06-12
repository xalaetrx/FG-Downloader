# FG Downloader

A lightweight, minimal, and native desktop downloader for FitGirl Repacks. 
It bypasses P2P torrenting by scraping, resolving, and sequentially downloading direct-link parts from supported file hosters (such as FuckingFast and DataNodes).

## Quick Start (Pre-built Executable)

If you just want to run the application directly:
1. Download the latest pre-built executable from the [Releases](https://github.com/xalaetrx/FG-Downloader/releases) page.
2. Run `FG Downloader.exe` on your Windows machine.

---

## Development & Running from Source

If you prefer to run or build the application yourself, follow these instructions.

### Requirements

- **Python 3.10+** (Windows environment is recommended, as Dear PyGui uses native Windows handles for window management features).

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/xalaetrx/FG-Downloader.git
   cd FG-Downloader
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

To run the application directly without building:
```bash
python gui.py
```

### Building the Executable

You can compile the script into a single, standalone executable using PyInstaller:

1. Install PyInstaller (if not already installed):
   ```bash
   pip install pyinstaller
   ```

2. Compile the package:
   ```bash
   pyinstaller --noconfirm --onedir --windowed --add-data "favicon.ico;." --icon "favicon.ico" gui.py
   ```
   *(Note: The build configuration utilizes PyInstaller's resource bundling to fetch files at runtime.)*
