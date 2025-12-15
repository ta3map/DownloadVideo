# Video Downloader

A simple desktop application for downloading videos from various platforms using yt-dlp.

## Features

- Download videos in various formats
- Audio-only extraction (MP3)
- Download queue with up to 3 simultaneous downloads
- Download history tracking
- UI state persistence
- SQLite database for data storage

## Requirements

- Python 3.12+
- Flask
- pywebview
- yt-dlp
- ffmpeg (optional, for format merging)

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install flask pywebview yt-dlp
```

3. Run the application:
```bash
python app.py
```

## Usage

1. Enter video URL
2. Select download folder
3. Choose format or enable audio-only mode
4. Add to queue
5. Start download

## Screenshots

### Main Interface
![Main Interface](screenshots/main.png)

### Queue Management
![Queue Management](screenshots/queue.png)

### Download History
![Download History](screenshots/history.png)

## License

MIT

