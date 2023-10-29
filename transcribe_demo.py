# ! python3.7

import argparse
import io
import os
import speech_recognition as sr
import whisper
import torch
import pyttsx3
import subprocess
from wakeonlan import send_magic_packet
import multiprocessing
import requests
import pytube
from pydub import AudioSegment
from pydub.playback import play
import tempfile
import isodate
import shutil

from sys import platform
from datetime import datetime, timedelta
from queue import Queue
from tempfile import NamedTemporaryFile
from time import sleep
from vertexai.language_models import ChatModel, InputOutputTextPair
from google.cloud import aiplatform

project_id = "ENTER_ID"
aiplatform.init(project=project_id)
engine = pyttsx3.init()
engine.setProperty('rate', 150)


def play_music(after_play):
    api_key = "YOUR_API_KEY"
    x = requests.get(
        f"https://youtube.googleapis.com/youtube/v3/search?part=snippet&maxResults=1&q={after_play}&type=video&key={api_key}")
    search_res = x.json()
    vid_id = search_res['items'][0]['id']['videoId']

    url = f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={vid_id}&key={api_key}"
    response = requests.get(url)
    data = response.json()
    duration = data['items'][0]['contentDetails']['duration']

    # Parse the duration using isodate and convert it to seconds
    video_duration_seconds = isodate.parse_duration(duration).total_seconds()

    if video_duration_seconds < 400:
        video_url = f"https://www.youtube.com/watch?v={vid_id}"

        try:
            temp_dir = os.path.join(tempfile.gettempdir(), "youtube_songs")
            # Download the video
            yt = pytube.YouTube(video_url)
            audio_stream = yt.streams.filter(only_audio=True).first()
            audio_stream.download(output_path=temp_dir)
            # Get the downloaded file's path
            audio_file = os.path.join(temp_dir, audio_stream.default_filename)
            # Convert the audio to an AudioSegment for playback
            audio = AudioSegment.from_file(audio_file)
            # Play the audio
            play(audio)
            if os.path.isdir(r"PATH/TO/TEMP/YT_SONGS"):
                shutil.rmtree(r"PATH/TO/TEMP/YT_SONGS", ignore_errors=True)
        except:
            engine.say("Something went wrong, try again")
            engine.runAndWait()

    else:
        engine.say("That's too long bozo")
        engine.runAndWait()


# function running in a new thread
def generate_response_as_thanos(afterthanos):
    chat_model = ChatModel.from_pretrained("chat-bison@001")

    chat = chat_model.start_chat(
        context="You are Thanos from Marvel and also my personal assistant.",
        examples=[
            InputOutputTextPair(
                input_text="Who do you work for?",
                output_text="Enter your name",
            ),
        ],
        temperature=0.3,
    )

    response = chat.send_message(afterthanos)
    print(f"Response from Model: {response.text}")
    engine.say(response.text)
    engine.runAndWait()


def main():
    # for wakeonlan
    mac_address = "your_mac_address"

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="tiny", help="Model to use",
                        choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--non_english", action='store_true',
                        help="Don't use the english model.")
    parser.add_argument("--energy_threshold", default=1000,
                        help="Energy level for mic to detect.", type=int)
    parser.add_argument("--record_timeout", default=2,
                        help="How real time the recording is in seconds.", type=float)
    parser.add_argument("--phrase_timeout", default=3,
                        help="How much empty space between recordings before we "
                             "consider it a new line in the transcription.", type=float)
    if 'linux' in platform:
        parser.add_argument("--default_microphone", default='pulse',
                            help="Default microphone name for SpeechRecognition. "
                                 "Run this with 'list' to view available Microphones.", type=str)
    args = parser.parse_args()

    # The last time a recording was retrieved from the queue.
    phrase_time = None
    # Current raw audio bytes.
    last_sample = bytes()
    # Thread safe Queue for passing data from the threaded recording callback.
    data_queue = Queue()
    # We use SpeechRecognizer to record our audio because it has a nice feature where it can detect when speech ends.
    recorder = sr.Recognizer()
    recorder.energy_threshold = args.energy_threshold
    # Definitely do this, dynamic energy compensation lowers the energy threshold dramatically to a point where the
    # SpeechRecognizer never stops recording.
    recorder.dynamic_energy_threshold = False

    # Important for linux users.
    # Prevents permanent application hang and crash by using the wrong Microphone
    if 'linux' in platform:
        mic_name = args.default_microphone
        if not mic_name or mic_name == 'list':
            print("Available microphone devices are: ")
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                print(f"Microphone with name \"{name}\" found")
            return
        else:
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                if mic_name in name:
                    source = sr.Microphone(sample_rate=16000, device_index=index)
                    break
    else:
        source = sr.Microphone(sample_rate=16000)

    # Load / Download model
    model = args.model
    if args.model != "large" and not args.non_english:
        model = model + ".en"
    audio_model = whisper.load_model(model)

    record_timeout = args.record_timeout
    phrase_timeout = args.phrase_timeout

    temp_file = NamedTemporaryFile().name

    with source:
        recorder.adjust_for_ambient_noise(source)

    def record_callback(_, audio: sr.AudioData) -> None:
        """
        Threaded callback function to receive audio data when recordings finish.
        audio: An AudioData containing the recorded bytes.
        """
        # Grab the raw bytes and push it into the thread safe queue.
        data = audio.get_raw_data()
        data_queue.put(data)

    # Create a background thread that will pass us raw audio bytes.
    # We could do this manually but SpeechRecognizer provides a nice helper.
    recorder.listen_in_background(source, record_callback, phrase_time_limit=record_timeout)

    # Cue the user that we're ready to go.
    print("Model loaded.\n")
    while True:
        try:
            now = datetime.utcnow()
            # Pull raw recorded audio from the queue.
            if not data_queue.empty():
                phrase_complete = False
                # If enough time has passed between recordings, consider the phrase complete.
                # Clear the current working audio buffer to start over with the new data.
                if phrase_time and now - phrase_time > timedelta(seconds=phrase_timeout):
                    last_sample = bytes()
                    phrase_complete = True
                # This is the last time we received new audio data from the queue.
                phrase_time = now

                # Concatenate our current audio data with the latest audio data.
                while not data_queue.empty():
                    data = data_queue.get()
                    last_sample += data

                # Use AudioData to convert the raw data to wav data.
                audio_data = sr.AudioData(last_sample, source.SAMPLE_RATE, source.SAMPLE_WIDTH)
                wav_data = io.BytesIO(audio_data.get_wav_data())

                # Write wav data to the temporary file as bytes.
                with open(temp_file, 'w+b') as f:
                    f.write(wav_data.read())

                # Read the transcription.
                result = audio_model.transcribe(temp_file, fp16=torch.cuda.is_available())
                text = result['text'].strip()

                text_lower = text.lower()

                if 'fennos' in text_lower or 'fenno' in text_lower or 'fennus' in text_lower:
                    text_lower = text_lower.replace('fennos', 'thanos').replace('fenno', 'thanos').replace('fennus',
                                                                                                           'thanos')

                print(text_lower)

                # ssh details
                user = "N/a"
                host = "N/a"
                cmd = "shutdown /s /f /t 0"

                # analyzing words after 'thanos' with chatgpt
                if 'thanos' in text_lower:
                    try:
                        response_process.terminate()
                    except:
                        pass
                    try:
                        music_process.terminate()
                    except:
                        pass
                    try:
                        if os.path.isdir(r"PATH/TO/TEMP/YT_SONGS"):
                            shutil.rmtree(r"PATH/TO/TEMP/YT_SONGS", ignore_errors=True)
                    except Exception as e:
                        print(e)
                    try:
                        if 'thanos stop' in text_lower or 'thanos, stop' in text_lower:
                            engine.say("Stopping")
                            engine.runAndWait()
                        elif 'thanos computer off' in text_lower or 'thanos, computer off' in text_lower:
                            engine.say("PC off")
                            engine.runAndWait()
                            subprocess.Popen(f"ssh {user}@{host} {cmd}", shell=True, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE).communicate()
                        # elif 'thanos computer on' in text_lower or 'thanos, computer on' in text_lower:
                        #     send_magic_packet(mac_address)
                        elif 'thanos play' in text_lower or 'thanos, play' in text_lower:
                            engine.say("Sure!")
                            engine.runAndWait()
                            play_index = text_lower.index('play')
                            words_after_play = text_lower[play_index + 4:]
                            music_process = multiprocessing.Process(target=play_music, args=(words_after_play,))
                            music_process.start()
                        else:
                            index = text_lower.index('thanos')
                            words_after_thanos = text_lower[index + 6:]
                            engine.say("One moment master")
                            engine.runAndWait()
                            response_process = multiprocessing.Process(target=generate_response_as_thanos,
                                                                       args=(words_after_thanos,))
                            response_process.start()
                    except:
                        engine.say("I'm confused, try again buddy.")
                        engine.runAndWait()

                # remove the temp file after usage
                os.remove(temp_file)

                # Clear the console to reprint the updated transcription.
                os.system('cls' if os.name == 'nt' else 'clear')
                # Flush stdout.
                print('', end='', flush=True)

                # Infinite loops are bad for processors, must sleep.
                sleep(0.25)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
