# Thanos Voice Assistant

A voice assistant that listens through your default microphone and responds through your output (speakers/headphones).

If you're using the vertexai for the personal assistant follow [`these steps`](https://cloud.google.com/vertex-ai/docs/start/client-libraries#python) and at the bottom be sure to also install the python SDK for it.

To run every function of this program you will need an API key for youtube.

To install dependencies simply run
```
pip install -r requirements.txt
```
in an environment of your choosing.

Also follow the setup for [`whisper`](https://github.com/openai/whisper#setup).

Make sure your venv is inheriting global site packages.

Whisper also requires the command-line tool [`ffmpeg`](https://ffmpeg.org/) to be installed on your system, which is available from most package managers:

```
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on Arch Linux
sudo pacman -S ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Chocolatey (https://chocolatey.org/)
choco install ffmpeg

# on Windows using Scoop (https://scoop.sh/)
scoop install ffmpeg
```
