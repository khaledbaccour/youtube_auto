from moviepy import *
import os


def assemble_video(frame_paths, audio_paths, output_path="output/video.mp4"):
    """
    Assemble final video from frames and audio. No subtitles.

    Args:
        frame_paths: list of PNG image paths (one per scene)
        audio_paths: list of WAV/MP3 audio paths (one per scene)
        output_path: where to save the final MP4
    """
    os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

    scene_clips = []

    for i, (frame_path, audio_path) in enumerate(zip(frame_paths, audio_paths)):
        audio_clip = AudioFileClip(audio_path)
        scene_duration = audio_clip.duration

        img_clip = ImageClip(frame_path).with_duration(scene_duration)
        img_clip = img_clip.resized((1920, 1080))
        img_clip = img_clip.with_audio(audio_clip)

        scene_clips.append(img_clip)

    if not scene_clips:
        print("ERROR: No scene clips were created.")
        return

    # Hard cuts between scenes — no crossfade to avoid audio overlap
    final = concatenate_videoclips(scene_clips, method="chain")
    final = final.with_fps(30)

    print(f"  Exporting video ({final.duration:.1f}s) to {output_path}...")
    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    print(f"  Video saved: {output_path}")


def assemble_video_continuous(frame_paths, scene_durations, audio_path, output_path="output/video.mp4"):
    """
    Assemble video from frames with a single continuous audio track.
    Visuals change at calculated timestamps while audio flows uninterrupted.

    Args:
        frame_paths: list of PNG image paths (one per scene)
        scene_durations: list of floats (seconds per scene, from calculate_scene_durations)
        audio_path: single WAV file path for the full narration
        output_path: where to save the final MP4
    """
    os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

    # Load the single continuous audio track
    audio_clip = AudioFileClip(audio_path)

    # Create image clips with calculated durations
    scene_clips = []
    for i, (frame_path, duration) in enumerate(zip(frame_paths, scene_durations)):
        img_clip = ImageClip(frame_path).with_duration(duration)
        img_clip = img_clip.resized((1920, 1080))
        scene_clips.append(img_clip)

    if not scene_clips:
        print("ERROR: No scene clips were created.")
        return

    # Concatenate visual clips (hard cuts between visuals)
    video = concatenate_videoclips(scene_clips, method="chain")

    # Overlay the single continuous audio track
    video = video.with_audio(audio_clip)
    video = video.with_fps(30)

    print(f"  Exporting video ({video.duration:.1f}s) to {output_path}...")
    video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    print(f"  Video saved: {output_path}")


if __name__ == "__main__":
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs("output", exist_ok=True)
    test_frames = []
    colors = [(44, 62, 80), (39, 174, 96)]
    labels = ["Scene 1: Test Frame", "Scene 2: Another Frame"]

    for idx, (color, label) in enumerate(zip(colors, labels)):
        img = Image.new("RGB", (1920, 1080), color)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 72)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            ((1920 - text_w) // 2, (1080 - text_h) // 2),
            label,
            fill="white",
            font=font,
        )
        path = f"output/test_frame_{idx}.png"
        img.save(path)
        test_frames.append(path)

    print("Test frames created. To run full assembly, provide audio files.")
    print(f"Frames: {test_frames}")
