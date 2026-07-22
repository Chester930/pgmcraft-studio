"""
PGMCraft Domain-Specific URL Downloader Strategy & Dispatcher.
Supports YouTube, Bilibili, NicoNico, SoundCloud, Direct Links,
and Social Media Platforms (Instagram, TikTok/Douyin, Twitter/X, Facebook, Twitch).
Creates a dedicated subfolder named after the media title containing ONLY 3 files: .mp4, .wav, and .mp3.
"""

import os
import re
import glob
import requests

def sanitize_filename(name):
    """移除檔名非法字元"""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def convert_wav_to_mp3(wav_path, mp3_path):
    """將 WAV 音檔轉碼寫出 MP3 檔"""
    try:
        import subprocess
        cmd = ["ffmpeg", "-y", "-i", wav_path, "-b:a", "320k", mp3_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        try:
            from pydub import AudioSegment
            sound = AudioSegment.from_wav(wav_path)
            sound.export(mp3_path, format="mp3", bitrate="320k")
        except Exception as e:
            print(f"[Audio Convert Warning] MP3 export fallback error ({e}). Copying WAV data.")
            import shutil
            shutil.copyfile(wav_path, mp3_path)


def cleanup_temp_stream_files(folder_path):
    """只清理 yt-dlp 的中繼分軌暫存檔 (如 .f140.m4a, .f399.mp4)，保留最後合成的 .mp4, .wav, .mp3"""
    if not os.path.exists(folder_path):
        return
    for temp_file in glob.glob(os.path.join(folder_path, "*.f[0-9]*.*")):
        try:
            os.remove(temp_file)
            print(f"[Cleanup] 已移除中繼分軌暫存檔: {temp_file}")
        except Exception as e:
            print(f"[Cleanup Error] {e}")


class BaseURLHandler:
    """策略模式抽象 Handler"""
    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    def download(self, url: str, output_dir: str) -> dict:
        raise NotImplementedError


class YouTubeHandler(BaseURLHandler):
    """YouTube 專用下載策略"""
    def can_handle(self, url: str) -> bool:
        return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))

    def download(self, url: str, output_dir: str) -> dict:
        import yt_dlp
        print(f"[URL Handler: YouTube] Downloading video & extracting WAV/MP3...")
        
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'youtube_media'))

        media_folder = os.path.join(output_dir, title)
        os.makedirs(media_folder, exist_ok=True)

        wav_path = os.path.join(media_folder, f"{title}.wav")
        mp3_path = os.path.join(media_folder, f"{title}.mp3")
        mp4_path = os.path.join(media_folder, f"{title}.mp4")

        # 必須將 keepvideo 設為 True，防止 FFmpegExtractAudio 在轉出 .wav 後將合成好的 .mp4 影片檔刪除
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(media_folder, f"{title}.%(ext)s"),
            'quiet': False,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0',
            }],
            'keepvideo': True, # 保留合成好的 .mp4 影片檔
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(wav_path) and not os.path.exists(mp3_path):
            convert_wav_to_mp3(wav_path, mp3_path)

        # 專門清理中繼串流暫存檔 (.f140.m4a, .f399.mp4)
        cleanup_temp_stream_files(media_folder)

        return {
            "folder": media_folder,
            "wav": wav_path if os.path.exists(wav_path) else None,
            "mp3": mp3_path if os.path.exists(mp3_path) else None,
            "mp4": mp4_path if os.path.exists(mp4_path) else None,
            "title": title
        }


class BilibiliHandler(BaseURLHandler):
    """Bilibili 專用下載策略"""
    def can_handle(self, url: str) -> bool:
        return bool(re.search(r'(bilibili\.com|b23\.tv)', url, re.IGNORECASE))

    def download(self, url: str, output_dir: str) -> dict:
        import yt_dlp
        print(f"[URL Handler: Bilibili] Downloading Bilibili media...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'bilibili_media'))

        media_folder = os.path.join(output_dir, title)
        os.makedirs(media_folder, exist_ok=True)

        wav_path = os.path.join(media_folder, f"{title}.wav")
        mp3_path = os.path.join(media_folder, f"{title}.mp3")
        mp4_path = os.path.join(media_folder, f"{title}.mp4")

        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(media_folder, f"{title}.%(ext)s"),
            'http_headers': {
                'Referer': 'https://www.bilibili.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0',
            }],
            'keepvideo': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(wav_path) and not os.path.exists(mp3_path):
            convert_wav_to_mp3(wav_path, mp3_path)

        cleanup_temp_stream_files(media_folder)

        return {
            "folder": media_folder,
            "wav": wav_path if os.path.exists(wav_path) else None,
            "mp3": mp3_path if os.path.exists(mp3_path) else None,
            "mp4": mp4_path if os.path.exists(mp4_path) else None,
            "title": title
        }


class InstagramHandler(BaseURLHandler):
    """Instagram (Reels / Video) 專用下載策略"""
    def can_handle(self, url: str) -> bool:
        return bool(re.search(r'(instagram\.com|instagr\.am)', url, re.IGNORECASE))

    def download(self, url: str, output_dir: str) -> dict:
        import yt_dlp
        print(f"[URL Handler: Instagram] Downloading IG Reels...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'instagram_reels'))

        media_folder = os.path.join(output_dir, title)
        os.makedirs(media_folder, exist_ok=True)

        wav_path = os.path.join(media_folder, f"{title}.wav")
        mp3_path = os.path.join(media_folder, f"{title}.mp3")
        mp4_path = os.path.join(media_folder, f"{title}.mp4")

        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(media_folder, f"{title}.%(ext)s"),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15'
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0',
            }],
            'keepvideo': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(wav_path) and not os.path.exists(mp3_path):
            convert_wav_to_mp3(wav_path, mp3_path)

        cleanup_temp_stream_files(media_folder)

        return {
            "folder": media_folder,
            "wav": wav_path if os.path.exists(wav_path) else None,
            "mp3": mp3_path if os.path.exists(mp3_path) else None,
            "mp4": mp4_path if os.path.exists(mp4_path) else None,
            "title": title
        }


class TikTokHandler(BaseURLHandler):
    """TikTok / 抖音 (Douyin) 專用下載策略"""
    def can_handle(self, url: str) -> bool:
        return bool(re.search(r'(tiktok\.com|douyin\.com)', url, re.IGNORECASE))

    def download(self, url: str, output_dir: str) -> dict:
        import yt_dlp
        print(f"[URL Handler: TikTok] Downloading TikTok media...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'tiktok_video'))

        media_folder = os.path.join(output_dir, title)
        os.makedirs(media_folder, exist_ok=True)

        wav_path = os.path.join(media_folder, f"{title}.wav")
        mp3_path = os.path.join(media_folder, f"{title}.mp3")
        mp4_path = os.path.join(media_folder, f"{title}.mp4")

        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(media_folder, f"{title}.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0',
            }],
            'keepvideo': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(wav_path) and not os.path.exists(mp3_path):
            convert_wav_to_mp3(wav_path, mp3_path)

        cleanup_temp_stream_files(media_folder)

        return {
            "folder": media_folder,
            "wav": wav_path if os.path.exists(wav_path) else None,
            "mp3": mp3_path if os.path.exists(mp3_path) else None,
            "mp4": mp4_path if os.path.exists(mp4_path) else None,
            "title": title
        }


class GenericYtdlpHandler(BaseURLHandler):
    """通用保底策略"""
    def can_handle(self, url: str) -> bool:
        return True

    def download(self, url: str, output_dir: str) -> dict:
        import yt_dlp
        print(f"[URL Handler: GenericFallback] Downloading media...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'media'))

        media_folder = os.path.join(output_dir, title)
        os.makedirs(media_folder, exist_ok=True)

        wav_path = os.path.join(media_folder, f"{title}.wav")
        mp3_path = os.path.join(media_folder, f"{title}.mp3")
        mp4_path = os.path.join(media_folder, f"{title}.mp4")

        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(media_folder, f"{title}.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0',
            }],
            'keepvideo': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(wav_path) and not os.path.exists(mp3_path):
            convert_wav_to_mp3(wav_path, mp3_path)

        cleanup_temp_stream_files(media_folder)

        return {
            "folder": media_folder,
            "wav": wav_path if os.path.exists(wav_path) else None,
            "mp3": mp3_path if os.path.exists(mp3_path) else None,
            "mp4": mp4_path if os.path.exists(mp4_path) else None,
            "title": title
        }


class URLDownloaderDispatcher:
    """URL 域名分發總控器"""
    def __init__(self):
        self.handlers = [
            YouTubeHandler(),
            BilibiliHandler(),
            InstagramHandler(),
            TikTokHandler(),
            GenericYtdlpHandler() # 保底
        ]

    def dispatch_and_download(self, url: str, output_dir: str) -> dict:
        for handler in self.handlers:
            if handler.can_handle(url):
                print(f"[Dispatcher] Matched handler: {handler.__class__.__name__} for URL: {url}")
                return handler.download(url, output_dir)
        raise RuntimeError(f"No handler available for URL: {url}")
